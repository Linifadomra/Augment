//    Augment Copyright (C) 2026 Liam
//
//    This program is free software: you can redistribute it and/or modify
//    it under the terms of the GNU General Public License as published by
//    the Free Software Foundation, either version 3 of the License, or
//    (at your option) any later version.
//
//    This program is distributed in the hope that it will be useful,
//    but WITHOUT ANY WARRANTY; without even the implied warranty of
//    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
//    GNU General Public License for more details.
//
//    You should have received a copy of the GNU General Public License
//    along with this program.  If not, see <https://www.gnu.org/licenses/>.

#include <cstdint>
#include <cstring>

#include "augment_exclusions.hpp"

#if defined(__APPLE__) || defined(__linux__)

#include <cstdlib>
#include <cxxabi.h>

namespace augment::plat {
namespace {

bool macho_name_equal(const char* macho, const char* query) {
    if (!macho || !query) return false;
    if (std::strcmp(macho, query) == 0) return true;
    // Mach-O strtab uses a leading '_' plus Itanium '_ZN...' => '__ZN...'.
    if (macho[0] == '_' && std::strcmp(macho + 1, query) == 0) return true;
    if (query[0] == '_' && std::strcmp(macho, query + 1) == 0) return true;
    return false;
}

bool flat_name_matches(const char* dem, const char* query) {
    while (*query) {
        if (*query == '_') {
            if (dem[0] == ':' && dem[1] == ':') {
                dem += 2;
                query++;
                continue;
            }
        }
        if (*dem != *query) return false;
        dem++;
        query++;
    }
    return *dem == '\0' || *dem == '(';
}

bool name_matches(const char* itanium, const char* query) {
    if (macho_name_equal(itanium, query)) return true;

    // Mach-O exports Itanium symbols as "_ZN..."; callers may pass "ZN...".
    char scratch[512];
    const char* demangle_input = itanium;
    if (itanium[0] == '_' && itanium[1] == '_') {
        demangle_input = itanium + 1;
    } else if (itanium[0] == 'Z') {
        scratch[0] = '_';
        std::strncpy(scratch + 1, itanium, sizeof(scratch) - 2);
        scratch[sizeof(scratch) - 1] = '\0';
        demangle_input = scratch;
    } else if (itanium[0] != '_' || itanium[1] != 'Z') {
        return false;
    }

    int   status = 0;
    char* dem    = abi::__cxa_demangle(demangle_input, nullptr, nullptr, &status);
    if (!dem) return false;

    const bool ok = flat_name_matches(dem, query);
    std::free(dem);
    return ok;
}

} // namespace
} // namespace augment::plat

#endif

#if defined(__APPLE__)

#include <mach-o/dyld.h>
#include <mach-o/loader.h>
#include <mach-o/nlist.h>
#include <dlfcn.h>

namespace augment::plat {

namespace {

struct image_syms {
    const struct nlist_64* syms  = nullptr;
    const char*            strs  = nullptr;
    uint32_t               count = 0;
    intptr_t               slide = 0;
    bool                   ok    = false;
};

image_syms load_image() {
    image_syms out;
    for (uint32_t i = 0; i < _dyld_image_count(); ++i) {
        auto* hdr = reinterpret_cast<const struct mach_header_64*>(_dyld_get_image_header(i));
        if (!hdr || hdr->filetype != MH_EXECUTE) continue;

        intptr_t slide = _dyld_get_image_vmaddr_slide(i);
        const struct symtab_command* symtab = nullptr;
        uint64_t linkedit = 0;

        auto* lc = reinterpret_cast<const struct load_command*>(hdr + 1);
        for (uint32_t c = 0; c < hdr->ncmds; ++c) {
            if (lc->cmd == LC_SEGMENT_64) {
                auto* seg = reinterpret_cast<const struct segment_command_64*>(lc);
                if (std::strcmp(seg->segname, "__LINKEDIT") == 0)
                    linkedit = static_cast<uint64_t>(slide) + seg->vmaddr - seg->fileoff;
            } else if (lc->cmd == LC_SYMTAB) {
                symtab = reinterpret_cast<const struct symtab_command*>(lc);
            }
            lc = reinterpret_cast<const struct load_command*>(
                reinterpret_cast<const uint8_t*>(lc) + lc->cmdsize);
        }

        if (!symtab || !linkedit) continue;
        out.syms  = reinterpret_cast<const struct nlist_64*>(linkedit + symtab->symoff);
        out.strs  = reinterpret_cast<const char*>(linkedit + symtab->stroff);
        out.count = symtab->nsyms;
        out.slide = slide;
        out.ok    = true;
        return out;
    }
    return out;
}

const image_syms& image() {
    static const image_syms img = load_image();
    return img;
}

} // namespace

void* sym_resolve(const char* symbol) {
    if (!symbol) return nullptr;

    int   status   = 0;
    char* dem      = abi::__cxa_demangle(symbol, nullptr, nullptr, &status);
    bool  excluded = augment::augment_should_exclude(dem ? dem : symbol);
    std::free(dem);
    if (excluded) return nullptr;

    if (void* p = dlsym(RTLD_DEFAULT, symbol)) return p;
    if (symbol[0] != '_') {
        char scratch[512];
        scratch[0] = '_';
        std::strncpy(scratch + 1, symbol, sizeof(scratch) - 2);
        scratch[sizeof(scratch) - 1] = '\0';
        if (void* p = dlsym(RTLD_DEFAULT, scratch)) return p;
    }

    const image_syms& img = image();
    if (!img.ok) return nullptr;

    for (uint32_t i = 0; i < img.count; ++i) {
        const struct nlist_64& s = img.syms[i];
        if ((s.n_type & N_TYPE) != N_SECT || s.n_value == 0 || s.n_un.n_strx == 0) continue;
        const char* name = img.strs + s.n_un.n_strx;
        if (macho_name_equal(name, symbol) ||
            (name[0] == '_' && name_matches(name, symbol)))
            return reinterpret_cast<void*>(static_cast<uint64_t>(s.n_value) +
                                           static_cast<uint64_t>(img.slide));
    }
    return nullptr;
}

intptr_t image_slide() { return _dyld_get_image_vmaddr_slide(0); }

uintptr_t image_base() {
    const image_syms& img = image();
    return img.ok ? static_cast<uintptr_t>(img.slide) : 0;
}

uint64_t func_gap(void* target) {
    const image_syms& img = image();
    if (!img.ok) return UINT64_MAX;

    uint64_t at   = reinterpret_cast<uint64_t>(target);
    uint64_t best = UINT64_MAX;
    for (uint32_t i = 0; i < img.count; ++i) {
        const struct nlist_64& s = img.syms[i];
        if ((s.n_type & N_TYPE) != N_SECT || s.n_value == 0) continue;
        uint64_t addr = static_cast<uint64_t>(s.n_value) + static_cast<uint64_t>(img.slide);
        if (addr > at && addr - at < best) best = addr - at;
    }
    return best;
}

bool image_identity(uint64_t* guid_lo, uint64_t* guid_hi, uint32_t* age) {
    return false;
}

} // namespace augment::plat

#elif defined(__linux__)

#include <elf.h>
#include <link.h>

#include <cstdio>
#include <cstdlib>

namespace augment::plat {

namespace {

struct image_syms {
    const Elf64_Sym* syms  = nullptr;
    const char*      strs  = nullptr;
    size_t           count = 0;
    uintptr_t        bias  = 0;
    bool             ok    = false;
};

uintptr_t load_bias() {
    uintptr_t bias = 0;
    dl_iterate_phdr([](struct dl_phdr_info* info, size_t, void* out) -> int {
        *static_cast<uintptr_t*>(out) = info->dlpi_addr;
        return 1;
    }, &bias);
    return bias;
}

image_syms load_image() {
    image_syms out;
    FILE* f = std::fopen("/proc/self/exe", "rb");
    if (!f) return out;

    std::fseek(f, 0, SEEK_END);
    long size = std::ftell(f);
    std::fseek(f, 0, SEEK_SET);

    auto* buf = static_cast<uint8_t*>(std::malloc(static_cast<size_t>(size)));
    if (size <= 0 || !buf || std::fread(buf, 1, static_cast<size_t>(size), f) != static_cast<size_t>(size)) {
        std::fclose(f);
        std::free(buf);
        return out;
    }
    std::fclose(f);

    auto* eh = reinterpret_cast<const Elf64_Ehdr*>(buf);
    if (!eh->e_shoff || !eh->e_shnum) { std::free(buf); return out; }

    auto* sh = reinterpret_cast<const Elf64_Shdr*>(buf + eh->e_shoff);
    const Elf64_Shdr* symtab = nullptr;
    for (uint16_t i = 0; i < eh->e_shnum; ++i)
        if (sh[i].sh_type == SHT_SYMTAB) { symtab = &sh[i]; break; }
    if (!symtab) { std::free(buf); return out; }

    const Elf64_Shdr& strtab = sh[symtab->sh_link];
    out.syms  = reinterpret_cast<const Elf64_Sym*>(buf + symtab->sh_offset);
    out.strs  = reinterpret_cast<const char*>(buf + strtab.sh_offset);
    out.count = symtab->sh_size / sizeof(Elf64_Sym);
    out.bias  = load_bias();
    out.ok    = true;
    return out;
}

const image_syms& image() {
    static const image_syms img = load_image();
    return img;
}

} // namespace

void* sym_resolve(const char* symbol) {
    if (!symbol) return nullptr;

    int   status   = 0;
    char* dem      = abi::__cxa_demangle(symbol, nullptr, nullptr, &status);
    bool  excluded = augment::augment_should_exclude(dem ? dem : symbol);
    std::free(dem);
    if (excluded) return nullptr;

    const image_syms& img = image();
    if (!img.ok) return nullptr;

    for (size_t i = 0; i < img.count; ++i) {
        const Elf64_Sym& s = img.syms[i];
        if (s.st_value == 0 || s.st_name == 0) continue;
        if (name_matches(img.strs + s.st_name, symbol))
            return reinterpret_cast<void*>(img.bias + s.st_value);
    }
    return nullptr;
}

intptr_t image_slide() {
    return static_cast<intptr_t>(load_bias());
}

uintptr_t image_base() {
    const image_syms& img = image();
    return img.ok ? static_cast<uintptr_t>(img.bias) : 0;
}

bool image_identity(uint64_t* guid_lo, uint64_t* guid_hi, uint32_t* age) {
    return false;
}

uint64_t func_gap(void* target) {
    const image_syms& img = image();
    if (!img.ok) return UINT64_MAX;

    uint64_t at   = reinterpret_cast<uint64_t>(target);
    uint64_t best = UINT64_MAX;
    for (size_t i = 0; i < img.count; ++i) {
        const Elf64_Sym& s = img.syms[i];
        if (s.st_value == 0) continue;
        uint64_t addr = img.bias + s.st_value;
        if (addr > at && addr - at < best) best = addr - at;
    }
    return best;
}

} // namespace augment::plat

#elif defined(_WIN32)

#include <windows.h>
#include <dbghelp.h>

#include <mutex>
#include <string>
#include <unordered_map>

#pragma comment(lib, "dbghelp.lib")

namespace augment::plat {

namespace {

struct image_syms {
    HANDLE  process = nullptr;
    ULONG64 base    = 0;
    bool    ok      = false;
};

image_syms load_image() {
    image_syms out;

    HANDLE process = GetCurrentProcess();

    SymSetOptions(SYMOPT_UNDNAME | SYMOPT_DEFERRED_LOADS);

    if (!SymInitialize(process, nullptr, FALSE))
        return out;

    out.process = process;
    out.base    = reinterpret_cast<ULONG64>(GetModuleHandleW(nullptr));

    char modulePath[MAX_PATH];
    if (GetModuleFileNameA(reinterpret_cast<HMODULE>(out.base), modulePath, sizeof(modulePath))) {
        DWORD64 loadedBase = SymLoadModuleEx(
            process,
            nullptr,      // hFile
            modulePath,   // ImageName
            nullptr,      // ModuleName
            out.base,     // Force DbgHelp to relocate symbols to this base
            0,            // DllSize (0 = auto)
            nullptr,      // Data
            0             // Flags
        );

        if (loadedBase) {
            out.ok = true;
        }
    }

    return out;
}

const image_syms& image() {
    static const image_syms img = load_image();
    return img;
}

struct gap_context {
    uint64_t target = 0;
    uint64_t best   = UINT64_MAX;
};

} // namespace

void* sym_resolve(const char* symbol) {
    const image_syms& img = image();
    if (!symbol || !img.ok)
        return nullptr;

    static std::unordered_map<std::string, void*> s_resolveCache;
    static std::mutex s_resolveCacheMutex;
    {
        std::lock_guard<std::mutex> lock(s_resolveCacheMutex);
        auto it = s_resolveCache.find(symbol);
        if (it != s_resolveCache.end())
            return it->second;
    }

    char storage[sizeof(SYMBOL_INFO) + MAX_SYM_NAME];
    auto* info = reinterpret_cast<PSYMBOL_INFO>(storage);
    info->SizeOfStruct = sizeof(SYMBOL_INFO);
    info->MaxNameLen   = MAX_SYM_NAME;

    void* result = nullptr;
    if (SymFromName(img.process, symbol, info) &&
        !augment::augment_should_exclude(info->Name)) {
        result = reinterpret_cast<void*>(info->Address);
    }

    {
        std::lock_guard<std::mutex> lock(s_resolveCacheMutex);
        s_resolveCache.emplace(symbol, result);
    }
    return result;
}

static BOOL CALLBACK gap_enum_cb(PSYMBOL_INFO sym, ULONG, PVOID user) {
    auto* ctx = static_cast<gap_context*>(user);

    if (sym->Address > ctx->target) {
        uint64_t gap = sym->Address - ctx->target;
        if (gap < ctx->best)
            ctx->best = gap;
    }

    return TRUE;
}

uint64_t func_gap(void* target) {
    const image_syms& img = image();
    if (!target || !img.ok)
        return UINT64_MAX;

    gap_context ctx{
        reinterpret_cast<uint64_t>(target),
        UINT64_MAX
    };

    SymEnumSymbols(img.process, img.base, "*", gap_enum_cb, &ctx);

    return ctx.best;
}

intptr_t image_slide() {
    auto* base = reinterpret_cast<uint8_t*>(GetModuleHandleW(nullptr));
    if (!base) return 0;
    auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
    if (dos->e_magic != IMAGE_DOS_SIGNATURE) return 0;
    auto* nt = reinterpret_cast<const IMAGE_NT_HEADERS*>(base + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE) return 0;
    return reinterpret_cast<intptr_t>(base) - static_cast<intptr_t>(nt->OptionalHeader.ImageBase);
}

uintptr_t image_base() {
    return reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr));
}

bool image_identity(uint64_t* guid_lo, uint64_t* guid_hi, uint32_t* age) {
    auto* base = reinterpret_cast<const uint8_t*>(GetModuleHandleW(nullptr));
    if (!base) return false;
    auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
    if (dos->e_magic != IMAGE_DOS_SIGNATURE) return false;
    auto* nt = reinterpret_cast<const IMAGE_NT_HEADERS*>(base + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE) return false;

    const IMAGE_DATA_DIRECTORY& dir =
        nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_DEBUG];
    if (!dir.VirtualAddress || dir.Size < sizeof(IMAGE_DEBUG_DIRECTORY)) return false;

    auto* dbg = reinterpret_cast<const IMAGE_DEBUG_DIRECTORY*>(base + dir.VirtualAddress);
    const unsigned count = dir.Size / sizeof(IMAGE_DEBUG_DIRECTORY);
    for (unsigned i = 0; i < count; ++i) {
        if (dbg[i].Type != IMAGE_DEBUG_TYPE_CODEVIEW || !dbg[i].AddressOfRawData) continue;
        if (dbg[i].SizeOfData < 24) continue;
        const uint8_t* cv = base + dbg[i].AddressOfRawData;
        uint32_t sig;
        std::memcpy(&sig, cv, 4);
        if (sig != 0x53445352) continue;

        uint32_t d1; uint16_t d2, d3; uint8_t d4[8];
        std::memcpy(&d1, cv + 4, 4);
        std::memcpy(&d2, cv + 8, 2);
        std::memcpy(&d3, cv + 10, 2);
        std::memcpy(d4, cv + 12, 8);

        uint64_t lo = (static_cast<uint64_t>(d1) << 32) |
                      (static_cast<uint64_t>(d2) << 16) |
                       static_cast<uint64_t>(d3);
        uint64_t hi = 0;
        for (int b = 0; b < 8; ++b)
            hi = (hi << 8) | d4[b];

        uint32_t cv_age;
        std::memcpy(&cv_age, cv + 20, 4);

        if (guid_lo) *guid_lo = lo;
        if (guid_hi) *guid_hi = hi;
        if (age)     *age = cv_age;
        return true;
    }
    return false;
}

} // namespace augment::plat

#else
#error "augment: no symbol resolver for this platform"
#endif
