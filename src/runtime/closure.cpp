#include "augment/augment.hpp"

#include <ffi/ffi.h>

#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

namespace augment::plat {
void* sym_resolve(const char* symbol);
}

namespace {

struct Signature {
    bool                   is_member = false;
    ffi_type*              rtype     = &ffi_type_void;
    std::vector<ffi_type*> atypes;   // includes the implicit 'this' for members
};

struct Closure {
    std::string            symbol;
    bool                   is_member = false;
    ffi_cif                cif;
    std::vector<ffi_type*> atypes;
    ffi_closure*           closure   = nullptr;
    void*                  code      = nullptr;
};

std::unordered_map<std::string, Signature>& sig_table() {
    static std::unordered_map<std::string, Signature> t;
    return t;
}

std::unordered_map<std::string, Closure*>& closure_table() {
    static std::unordered_map<std::string, Closure*> t;
    return t;
}

ffi_type* ffi_from_kind(const std::string& k) {
    if (k == "void") return &ffi_type_void;
    if (k == "i8")   return &ffi_type_sint8;
    if (k == "u8")   return &ffi_type_uint8;
    if (k == "i16")  return &ffi_type_sint16;
    if (k == "u16")  return &ffi_type_uint16;
    if (k == "i32")  return &ffi_type_sint32;
    if (k == "u32")  return &ffi_type_uint32;
    if (k == "i64")  return &ffi_type_sint64;
    if (k == "u64")  return &ffi_type_uint64;
    if (k == "f32")  return &ffi_type_float;
    if (k == "f64")  return &ffi_type_double;
    return &ffi_type_pointer;
}

void register_sig(const std::string& sym, bool is_member,
                  const std::string& rtype, std::vector<std::string>& atypes) {
    Signature s;
    s.is_member = is_member;
    s.rtype     = ffi_from_kind(rtype);
    if (is_member)
        s.atypes.push_back(&ffi_type_pointer);
    for (auto& a : atypes)
        s.atypes.push_back(ffi_from_kind(a));
    sig_table()[sym] = std::move(s);
}

void closure_handler(ffi_cif* cif, void* ret, void** args, void* user) {
    Closure* c = static_cast<Closure*>(user);

    AugmentCtx ctx;
    ctx.self      = c->is_member ? *static_cast<void**>(args[0]) : nullptr;
    ctx.args      = c->is_member ? args + 1 : args;
    ctx.ret       = ret;
    ctx.cancelled = 0;
    ctx.user      = nullptr;

    void* orig = augment_before(c->symbol.c_str(), &ctx);
    if (orig)
        ffi_call(cif, reinterpret_cast<void (*)()>(orig), ret, args);
    augment_after(c->symbol.c_str(), &ctx);
}

} // namespace

extern "C" AUGMENT_API void augment_register_signature(const char* symbol, int is_member,
                                                       const char* rtype,
                                                       const char** atypes, unsigned nargs) {
    std::vector<std::string> a;
    for (unsigned i = 0; i < nargs; ++i)
        a.emplace_back(atypes[i]);
    register_sig(symbol, is_member != 0, rtype, a);
}

extern "C" AUGMENT_API int augment_load_signatures(const char* path) {
    std::ifstream f(path);
    if (!f)
        return 0;

    std::string line;
    int n = 0;
    while (std::getline(f, line)) {
        if (line.empty() || line[0] == '#')
            continue;
        std::istringstream ss(line);
        std::string sym, qualified, member, rtype, a;
        if (!(ss >> sym >> qualified >> member >> rtype))
            continue;
        std::vector<std::string> atypes;
        while (ss >> a)
            atypes.push_back(a);
        bool mem = member == "1";
        register_sig(sym, mem, rtype, atypes);
        if (qualified != sym)
            register_sig(qualified, mem, rtype, atypes);
        ++n;
    }
    return n;
}

extern "C" AUGMENT_API void* augment_make_closure(const char* symbol) {
    auto& ct  = closure_table();
    auto  cit = ct.find(symbol);
    if (cit != ct.end())
        return cit->second->code;

    auto sit = sig_table().find(symbol);
    if (sit == sig_table().end())
        return nullptr;
    const Signature& sig = sit->second;

    Closure* c    = new Closure();
    c->symbol     = symbol;
    c->is_member  = sig.is_member;
    c->atypes     = sig.atypes;

    c->closure = static_cast<ffi_closure*>(ffi_closure_alloc(sizeof(ffi_closure), &c->code));
    if (!c->closure) { delete c; return nullptr; }

    unsigned total = static_cast<unsigned>(c->atypes.size());
    if (ffi_prep_cif(&c->cif, FFI_DEFAULT_ABI, total, sig.rtype, c->atypes.data()) != FFI_OK) {
        delete c;
        return nullptr;
    }
    if (ffi_prep_closure_loc(c->closure, &c->cif, closure_handler, c, c->code) != FFI_OK) {
        delete c;
        return nullptr;
    }

    ct[symbol] = c;
    return c->code;
}

extern "C" AUGMENT_API void augment_call(const char* symbol, void** args, unsigned nargs) {
    (void)nargs;
    void* fn = augment::plat::sym_resolve(symbol);
    if (!fn)
        return;
    auto it = sig_table().find(symbol);
    if (it == sig_table().end())
        return;
    Signature& sig = it->second;

    ffi_cif cif;
    if (ffi_prep_cif(&cif, FFI_DEFAULT_ABI, static_cast<unsigned>(sig.atypes.size()),
                     sig.rtype, sig.atypes.data()) != FFI_OK)
        return;

    char retbuf[64];
    void* ret = (sig.rtype == &ffi_type_void) ? nullptr : static_cast<void*>(retbuf);
    ffi_call(&cif, reinterpret_cast<void (*)()>(fn), ret, args);
}
