#include "augment/manifest_internal.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>

using namespace augment::manifest;

int main() {
    Reader r;
    assert(r.load("fixtures/sample.manifest"));
    assert(r.version() == 2);

    assert(r.func_count("daCow_c_Execute") == 1);
    FuncView f{};
    assert(r.func_at("daCow_c_Execute", 0, &f));
    assert(std::strcmp(f.mangled, "_ZN7daCow_c7ExecuteEv") == 0);
    assert(f.member);
    assert(std::strcmp(f.self_view, "daCow_c") == 0);
    assert(f.rva == 0x801234);
    assert(f.nargs == 0);

    FuncView s{};
    assert(r.func_at("setStage", 0, &s));
    assert(s.nargs == 2);
    assert(std::strcmp(s.args[0].name, "stage") == 0);
    assert(std::strcmp(s.args[0].kind, "ptr") == 0);
    assert(std::strcmp(s.args[0].view, "daCph_c") == 0);
    assert(std::strcmp(s.args[1].kind, "i32") == 0);

    assert(r.func_count("init") == 2);

    FieldView fld{};
    assert(r.struct_field("daCow_c", "mName", &fld));
    assert(fld.offset == 64 && std::strcmp(fld.kind, "str") == 0 && fld.len == 8);
    int64_t v = 0;
    assert(r.enum_value("daCow_c::Action", "angry", &v) && v == 3);
    uint64_t addr = 0; const char* kind = nullptr;
    assert(r.global("g_dComIfG", &kind, &addr) && addr == 0x804000);

    assert(r.func_count("nope") == 0);
    std::printf("PASS manifest_read\n");
    return 0;
}
