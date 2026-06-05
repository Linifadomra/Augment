#include "augment/manifest_internal.hpp"
#include <fstream>
#include <cstring>

namespace augment::manifest {

namespace {
template <class T> T rd(const uint8_t* p) { T v; std::memcpy(&v, p, sizeof(T)); return v; }
}

bool Reader::load(const char* path) {
    std::ifstream f(path, std::ios::binary);
    if (!f) return false;
    m_buf.assign(std::istreambuf_iterator<char>(f), std::istreambuf_iterator<char>());
    if (m_buf.size() < 12 || std::memcmp(m_buf.data(), "AGMF", 4) != 0) return false;

    const uint8_t* b = reinterpret_cast<const uint8_t*>(m_buf.data());
    m_version = rd<uint32_t>(b + 4);
    uint32_t stlen = rd<uint32_t>(b + 8);
    m_stoff = 12;
    uint32_t off = 12 + stlen;

    m_index.assign(5, {});
    for (int s = 0; s < 5; ++s) {
        uint32_t n = rd<uint32_t>(b + off); off += 4;
        for (uint32_t i = 0; i < n; ++i) {
            uint32_t no = rd<uint32_t>(b + off), po = rd<uint32_t>(b + off + 4);
            off += 8;
            m_index[s].emplace(str(no), po);
        }
    }
    off += 4;
    m_pbase = off;

    each_function([this](const char* flat, const FuncView& fv) {
        m_rva.emplace(fv.mangled, fv.rva);
        m_flat_of.emplace(fv.mangled, flat);
    });
    return true;
}

void Reader::records(int section, const char* name, std::vector<const uint8_t*>& out) const {
    auto& idx = m_index[section];
    auto it = idx.find(name);
    if (it == idx.end()) return;
    const uint8_t* p = reinterpret_cast<const uint8_t*>(m_buf.data()) + m_pbase + it->second;
    uint32_t count = rd<uint32_t>(p); p += 4;
    for (uint32_t i = 0; i < count; ++i) {
        uint32_t rec_len = rd<uint32_t>(p); p += 4;
        out.push_back(p);
        p += rec_len;
    }
}

void Reader::read_func(const uint8_t* p, FuncView* out) const {
    out->mangled   = str(rd<uint32_t>(p));      p += 4;
    out->member    = rd<uint8_t>(p) != 0;       p += 4;
    out->rva       = rd<uint64_t>(p);           p += 8;
    out->loc       = str(rd<uint32_t>(p));      p += 4;
    out->ret       = str(rd<uint32_t>(p));      p += 4;
    out->self_view = str(rd<uint32_t>(p));      p += 4;
    out->nargs     = rd<uint32_t>(p);           p += 4;
    m_argscratch.clear();
    for (uint32_t i = 0; i < out->nargs; ++i) {
        m_argscratch.push_back({ str(rd<uint32_t>(p)), str(rd<uint32_t>(p + 4)), str(rd<uint32_t>(p + 8)) });
        p += 12;
    }
    out->args = m_argscratch.data();
}

uint32_t Reader::func_count(const char* flat) const {
    std::vector<const uint8_t*> recs; records(0, flat, recs);
    return (uint32_t)recs.size();
}

bool Reader::func_at(const char* flat, uint32_t i, FuncView* out) const {
    std::vector<const uint8_t*> recs; records(0, flat, recs);
    if (i >= recs.size()) return false;
    read_func(recs[i], out);
    return true;
}

bool Reader::func_by_mangled(const char* mangled, FuncView* out) const {
    auto it = m_flat_of.find(mangled);
    if (it == m_flat_of.end()) return false;
    std::vector<const uint8_t*> recs; records(0, it->second.c_str(), recs);
    for (auto* p : recs) { read_func(p, out); if (std::strcmp(out->mangled, mangled) == 0) return true; }
    return false;
}

bool Reader::struct_field(const char* name, const char* field, FieldView* out) const {
    bool found = false;
    each_field(name, [&](const FieldView& fv) {
        if (!found && std::strcmp(fv.name, field) == 0) { *out = fv; found = true; }
    });
    return found;
}

bool Reader::enum_value(const char* name, const char* value_name, int64_t* out) const {
    bool found = false;
    each_enum_value(name, [&](const char* vn, int64_t v) {
        if (!found && std::strcmp(vn, value_name) == 0) { *out = v; found = true; }
    });
    return found;
}

bool Reader::global(const char* name, const char** kind_out, uint64_t* addr_out) const {
    std::vector<const uint8_t*> recs; records(3, name, recs);
    if (recs.empty()) return false;
    const uint8_t* p = recs[0];
    *kind_out = str(rd<uint32_t>(p));
    *addr_out = rd<uint64_t>(p + 4);
    return true;
}

uint64_t Reader::rva_of(const char* mangled) const {
    auto it = m_rva.find(mangled);
    return it == m_rva.end() ? 0 : it->second;
}

} // namespace augment::manifest
