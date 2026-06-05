#pragma once
#include <cstdint>
#include <cstring>
#include <string>
#include <unordered_map>
#include <vector>

namespace augment::manifest {

struct ArgView   { const char* name; const char* kind; const char* view; };
struct FuncView  { const char* mangled; bool member; const char* self_view; uint64_t rva;
                   const char* loc; const char* ret; const ArgView* args; uint32_t nargs; };
struct FieldView { const char* name; uint32_t offset; const char* kind; int32_t len; const char* view; };

class Reader {
public:
    bool load(const char* path);
    uint32_t version() const { return m_version; }

    uint32_t func_count(const char* flat) const;
    bool     func_at(const char* flat, uint32_t i, FuncView* out) const;
    bool     func_by_mangled(const char* mangled, FuncView* out) const;
    bool     struct_field(const char* name, const char* field, FieldView* out) const;
    bool     enum_value(const char* name, const char* value_name, int64_t* out) const;
    bool     global(const char* name, const char** kind_out, uint64_t* addr_out) const;
    uint64_t rva_of(const char* mangled) const;

    template <class F> void each_function(F&& cb) const {
        for (auto& kv : m_index[0]) {
            std::vector<const uint8_t*> recs; records(0, kv.first.c_str(), recs);
            for (auto* p : recs) { FuncView f{}; read_func(p, &f); cb(kv.first.c_str(), f); }
        }
    }
    template <class F> void each_field(const char* name, F&& cb) const {
        std::vector<const uint8_t*> recs; records(1, name, recs);
        if (recs.empty()) return;
        const uint8_t* p = recs[0];
        uint32_t nf = rdu32(p + 4); const uint8_t* q = p + 8;
        for (uint32_t i = 0; i < nf; ++i) {
            int32_t ln; std::memcpy(&ln, q + 12, 4);
            FieldView fv{ str(rdu32(q)), rdu32(q + 4), str(rdu32(q + 8)), ln, str(rdu32(q + 16)) };
            q += 20; cb(fv);
        }
    }
    template <class F> void each_enum_value(const char* name, F&& cb) const {
        std::vector<const uint8_t*> recs; records(2, name, recs);
        if (recs.empty()) return;
        const uint8_t* p = recs[0];
        uint32_t nv = rdu32(p + 4); const uint8_t* q = p + 8;
        for (uint32_t i = 0; i < nv; ++i) {
            int64_t v; std::memcpy(&v, q + 4, 8);
            const char* vn = str(rdu32(q)); q += 12; cb(vn, v);
        }
    }

private:
    const char* str(uint32_t off) const { return m_buf.data() + m_stoff + off; }
    static uint32_t rdu32(const uint8_t* p) { uint32_t v; std::memcpy(&v, p, 4); return v; }
    void records(int section, const char* name, std::vector<const uint8_t*>& out) const;
    void read_func(const uint8_t* p, FuncView* out) const;

    std::string m_buf;
    uint32_t m_version = 0;
    uint32_t m_stoff = 0;
    std::vector<std::unordered_map<std::string, uint32_t>> m_index;
    uint32_t m_pbase = 0;
    std::unordered_map<std::string, uint64_t> m_rva;
    std::unordered_map<std::string, std::string> m_flat_of;
    mutable std::vector<ArgView> m_argscratch;
};

} // namespace augment::manifest
