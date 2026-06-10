#include "augment/augment.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <cstdint>

int main() {
    struct S { int32_t a; float b; char name[8]; } s{};
    int32_t v = 42;
    augment_mem_write(&s, 0, "i32", &v);
    float fv = 3.5f;
    augment_mem_write(&s, 4, "f32", &fv);
    augment_mem_write_str(&s, 8, 8, "ABCDEFGHIJK");

    int32_t ra = 0; augment_mem_read(&s, 0, "i32", &ra);
    float   rb = 0; augment_mem_read(&s, 4, "f32", &rb);
    char    rn[8] = {}; int n = augment_mem_read_str(&s, 8, 8, rn);

    assert(ra == 42);
    assert(rb == 3.5f);
    assert(n == 7 && std::strcmp(rn, "ABCDEFG") == 0);
    std::printf("PASS mem\n");
    return 0;
}
