#include "augment/augment.hpp"
#include "augment/manifest_internal.hpp"
#include "internal.hpp"

#include <string>
#include <vector>
#include <set>
#include <functional>
#include <cstring>
#include <cstdint>

namespace augment::manifest { Reader& global_reader() { static Reader r; return r; } }

namespace augment::plat {
void* sym_resolve(const char* symbol);
intptr_t image_slide();
}

extern "C" AUGMENT_API int augment_manifest_load(const char* path) {
    using namespace augment::manifest;
    Reader& r = global_reader();
    if (!r.load(path)) return 0;
    int n = 0;
    std::set<std::string> registered;
    std::function<void(const char*)> ensure_struct = [&](const char* kind) {
        if (std::strncmp(kind, "struct:", 7) != 0) return;
        std::string name = kind + 7;
        if (!registered.insert(name).second) return;
        std::vector<std::string> mk;
        r.each_field(name.c_str(),
            [&](const FieldView& fv){ mk.emplace_back(fv.kind); });
        for (auto& k : mk) ensure_struct(k.c_str());
        std::vector<const char*> mp;
        for (auto& s : mk) mp.push_back(s.c_str());
        augment_register_struct(name.c_str(), mp.data(), (unsigned)mp.size());
    };
    r.each_function([&](const char* flat, const FuncView& fv) {
        ensure_struct(fv.ret);
        for (uint32_t i = 0; i < fv.nargs; ++i) ensure_struct(fv.args[i].kind);
        std::vector<const char*> atypes;
        for (uint32_t i = 0; i < fv.nargs; ++i) atypes.push_back(fv.args[i].kind);
        augment_register_signature(fv.mangled, fv.member ? 1 : 0, fv.ret,
                                   atypes.data(), (unsigned)atypes.size());
        if (flat && flat[0] && std::strcmp(flat, fv.mangled) != 0) {
            augment_register_signature(flat, fv.member ? 1 : 0, fv.ret,
                                       atypes.data(), (unsigned)atypes.size());
        }
        ++n;
    });
    return n;
}

extern "C" AUGMENT_API int augment_fn_count(const char* flat) {
    return (int)augment::manifest::global_reader().func_count(flat);
}

extern "C" AUGMENT_API const char* augment_fn_mangled(const char* flat, int i) {
    augment::manifest::FuncView f{};
    return augment::manifest::global_reader().func_at(flat, (uint32_t)i, &f) ? f.mangled : nullptr;
}

extern "C" AUGMENT_API const char* augment_fn_loc(const char* flat, int i) {
    augment::manifest::FuncView f{};
    return augment::manifest::global_reader().func_at(flat, (uint32_t)i, &f) ? f.loc : "";
}

extern "C" AUGMENT_API const char* augment_resolve_at(const char* flat, const char* file_substr) {
    auto& r = augment::manifest::global_reader();
    int n = (int)r.func_count(flat);
    for (int i = 0; i < n; ++i) {
        augment::manifest::FuncView f{};
        r.func_at(flat, (uint32_t)i, &f);
        if (std::strstr(f.loc, file_substr)) return f.mangled;
    }
    return nullptr;
}

extern "C" AUGMENT_API const char* augment_resolve_sig(const char* flat, const char* sig) {
    auto& r = augment::manifest::global_reader();
    int n = (int)r.func_count(flat);
    for (int i = 0; i < n; ++i) {
        augment::manifest::FuncView f{};
        r.func_at(flat, (uint32_t)i, &f);
        std::string s;
        for (uint32_t a = 0; a < f.nargs; ++a) { if (a) s += ","; s += f.args[a].kind; }
        if (s == sig) return f.mangled;
    }
    return nullptr;
}

extern "C" AUGMENT_API int augment_fn_params(const char* mangled, const AugmentArg** out) {
    static thread_local std::vector<AugmentArg> buf;
    auto& r = augment::manifest::global_reader();
    augment::manifest::FuncView f{};
    if (!r.func_by_mangled(mangled, &f)) { *out = nullptr; return 0; }
    buf.clear();
    for (uint32_t i = 0; i < f.nargs; ++i)
        buf.push_back({f.args[i].name, f.args[i].kind, f.args[i].view});
    *out = buf.data();
    return (int)buf.size();
}

extern "C" AUGMENT_API int augment_struct_fields(const char* name, const AugmentField** out) {
    static thread_local std::vector<AugmentField> buf;
    auto& r = augment::manifest::global_reader();
    buf.clear();
    r.each_field(name, [&](const augment::manifest::FieldView& fv) {
        buf.push_back({fv.name, fv.offset, fv.kind, fv.len, fv.view});
    });
    *out = buf.empty() ? nullptr : buf.data();
    return (int)buf.size();
}

extern "C" AUGMENT_API int augment_enum_values(const char* name, const AugmentEnumVal** out) {
    static thread_local std::vector<AugmentEnumVal> buf;
    auto& r = augment::manifest::global_reader();
    buf.clear();
    r.each_enum_value(name, [&](const char* vn, int64_t v) { buf.push_back({vn, (long long)v}); });
    *out = buf.empty() ? nullptr : buf.data();
    return (int)buf.size();
}

extern "C" AUGMENT_API int augment_global_addr(const char* name, const char** kind_out, void** addr_out) {
    uint64_t a = 0; const char* k = nullptr;
    if (!augment::manifest::global_reader().global(name, &k, &a)) return 0;
    *kind_out = k;
    if (void* resolved = augment::plat::sym_resolve(name)) {
        *addr_out = resolved;
        return 1;
    }
    *addr_out = reinterpret_cast<void*>((uintptr_t)(a + static_cast<uint64_t>(augment::plat::image_slide())));
    return 1;
}

extern "C" AUGMENT_API const char* augment_fn_self_view(const char* mangled) {
    augment::manifest::FuncView f{};
    return augment::manifest::global_reader().func_by_mangled(mangled, &f) ? f.self_view : "";
}

extern "C" AUGMENT_API const char* augment_fn_ret(const char* mangled) {
    augment::manifest::FuncView f{};
    return augment::manifest::global_reader().func_by_mangled(mangled, &f) ? f.ret : "void";
}

extern "C" AUGMENT_API void augment_mem_read(void* base, int offset, const char* kind, void* out) {
    if (!out) {
        augment_log("augment", "augment_mem_read: null 'out' pointer (base=%p, offset=%d, kind=%s)\n",
                base, offset, kind ? kind : "<null>");
        return;
    }
    if (!base) {
        augment_log("augment", "augment_mem_read: null 'base' pointer (offset=%d, kind=%s)\n",
                offset, kind ? kind : "<null>");
        return;
    }
    char* p = (char*)base + offset;
    if      (!std::strcmp(kind, "i8"))  *(int8_t*)out   = *(int8_t*)p;
    else if (!std::strcmp(kind, "u8"))  *(uint8_t*)out  = *(uint8_t*)p;
    else if (!std::strcmp(kind, "i16")) *(int16_t*)out  = *(int16_t*)p;
    else if (!std::strcmp(kind, "u16")) *(uint16_t*)out = *(uint16_t*)p;
    else if (!std::strcmp(kind, "i32")) *(int32_t*)out  = *(int32_t*)p;
    else if (!std::strcmp(kind, "u32")) *(uint32_t*)out = *(uint32_t*)p;
    else if (!std::strcmp(kind, "i64")) *(int64_t*)out  = *(int64_t*)p;
    else if (!std::strcmp(kind, "u64")) *(uint64_t*)out = *(uint64_t*)p;
    else if (!std::strcmp(kind, "f32")) *(float*)out    = *(float*)p;
    else if (!std::strcmp(kind, "f64")) *(double*)out   = *(double*)p;
    else                                 *(void**)out   = *(void**)p;
}

extern "C" AUGMENT_API void augment_mem_write(void* base, int offset, const char* kind, const void* in) {
    if (!in) {
        augment_log("augment", "augment_mem_write: null 'in' pointer (base=%p, offset=%d, kind=%s)\n",
                base, offset, kind ? kind : "<null>");
        return;
    }
    if (!base) {
        augment_log("augment", "augment_mem_write: null 'base' pointer (offset=%d, kind=%s)\n",
                offset, kind ? kind : "<null>");
        return;
    }
    char* p = (char*)base + offset;
    if      (!std::strcmp(kind, "i8"))  *(int8_t*)p   = *(const int8_t*)in;
    else if (!std::strcmp(kind, "u8"))  *(uint8_t*)p  = *(const uint8_t*)in;
    else if (!std::strcmp(kind, "i16")) *(int16_t*)p  = *(const int16_t*)in;
    else if (!std::strcmp(kind, "u16")) *(uint16_t*)p = *(const uint16_t*)in;
    else if (!std::strcmp(kind, "i32")) *(int32_t*)p  = *(const int32_t*)in;
    else if (!std::strcmp(kind, "u32")) *(uint32_t*)p = *(const uint32_t*)in;
    else if (!std::strcmp(kind, "i64")) *(int64_t*)p  = *(const int64_t*)in;
    else if (!std::strcmp(kind, "u64")) *(uint64_t*)p = *(const uint64_t*)in;
    else if (!std::strcmp(kind, "f32")) *(float*)p    = *(const float*)in;
    else if (!std::strcmp(kind, "f64")) *(double*)p   = *(const double*)in;
    else                                 *(void**)p   = *(void* const*)in;
}

extern "C" AUGMENT_API int augment_mem_read_str(void* base, int offset, int cap, char* out) {
    const char* p = (const char*)base + offset;
    int n = 0;
    while (n < cap && p[n]) { out[n] = p[n]; n++; }
    if (n < cap) out[n] = 0;
    return n;
}

extern "C" AUGMENT_API void augment_mem_write_str(void* base, int offset, int cap, const char* s) {
    char* p = (char*)base + offset;
    int n = (int)std::strlen(s);
    if (n > cap - 1) n = cap - 1;
    for (int i = 0; i < n; i++) p[i] = s[i];
    p[n] = 0;
}
