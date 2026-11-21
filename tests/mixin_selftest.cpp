// mixin_selftest.cpp

#include "augment/platform_compat.hpp"
#include "augment/augment.hpp"

#include <cstdio>
#include <cstdint>
#include <cstring>
#include <cstdarg>

#if defined(__linux__)
#include <csignal>
#include <unistd.h>
#include <ucontext.h>
#endif

namespace augtest {
AUGMENT_NOINLINE float scale(float base, float mul);
}

float augtest::scale(float base, float mul) {
    volatile float b = base;
    volatile float m = mul;
    return b * m;
}

static void step(const char* msg) {
    std::printf("[mixin] %s\n", msg);
    std::fflush(stdout);
}

static void dump_bytes(const char* tag, const void* p, int n) {
    const auto* b = static_cast<const unsigned char*>(p);
    std::printf("[mixin] %s @ %p:", tag, p);
    for (int i = 0; i < n; ++i)
        std::printf(" %02x", b[i]);
    std::printf("\n");
    std::fflush(stdout);
}

static void test_logger(const char* tag, const char* msg) {
    std::printf("[%s] %s\n", tag ? tag : "augment", msg ? msg : "");
    std::fflush(stdout);
}

#if defined(__linux__)
static void dump_bytes_fd(int fd, const char* tag, const void* p, int n) {
    char line[256];
    const auto* b = static_cast<const unsigned char*>(p);
    int len = std::snprintf(line, sizeof(line), "[mixin] %s @ %p:", tag, p);
    if (len < 0) len = 0;
    for (int i = 0; i < n && len < (int)sizeof(line) - 4; ++i)
        len += std::snprintf(line + len, sizeof(line) - (size_t)len, " %02x", b[i]);
    if (len < (int)sizeof(line) - 1) {
        line[len++] = '\n';
        line[len] = '\0';
    }
    (void)!write(fd, line, (size_t)len);
}

static void on_sigill(int, siginfo_t* info, void* uctx) {
    const void* fault = info ? info->si_addr : nullptr;
    char hdr[128];
    int n = std::snprintf(hdr, sizeof(hdr),
                          "[mixin] SIGILL si_addr=%p si_code=%d\n",
                          fault, info ? info->si_code : -1);
    if (n > 0) (void)!write(STDERR_FILENO, hdr, (size_t)n);
#if defined(__x86_64__) && defined(REG_RIP)
    auto* uc = static_cast<ucontext_t*>(uctx);
    if (uc) {
        const void* rip = reinterpret_cast<void*>(uc->uc_mcontext.gregs[REG_RIP]);
        n = std::snprintf(hdr, sizeof(hdr), "[mixin] SIGILL rip=%p\n", rip);
        if (n > 0) (void)!write(STDERR_FILENO, hdr, (size_t)n);
        if (rip) dump_bytes_fd(STDERR_FILENO, "bytes@rip", rip, 16);
    }
#else
    (void)uctx;
#endif
    if (fault) dump_bytes_fd(STDERR_FILENO, "bytes@si_addr", fault, 16);
    _exit(111);
}

static void install_sigill_handler() {
    struct sigaction sa{};
    sa.sa_sigaction = on_sigill;
    sa.sa_flags = SA_SIGINFO;
    sigemptyset(&sa.sa_mask);
    sigaction(SIGILL, &sa, nullptr);
}
#else
static void install_sigill_handler() {}
#endif

// Hand-written stand-in for what walk.py emits for augtest::scale.
static float dispatch_scale(float base, float mul) {
    step("dispatch_scale enter");
    void* __args[2] = { (void*)&base, (void*)&mul };
    float __ret{};
    AugmentCtx __actx = { nullptr, __args, (void*)&__ret, 0, nullptr };

    void* __saved = augment_before("augtest::scale", &__actx);
    std::printf("[mixin] dispatch: saved=%p base=%.1f mul=%.1f cancelled=%d\n",
                __saved, base, mul, __actx.cancelled);
    std::fflush(stdout);
    if (__saved) {
        dump_bytes("saved-entry", __saved, 16);
        step("dispatch_scale calling saved (orig trampoline)");
        __ret = reinterpret_cast<float(*)(float, float)>(__saved)(base, mul);
        std::printf("[mixin] dispatch: orig returned %.1f\n", __ret);
        std::fflush(stdout);
    } else {
        step("dispatch_scale: saved is null (cancelled or missing)");
    }
    augment_after("augtest::scale", &__actx);
    step("dispatch_scale leave");
    return __ret;
}

static void boost(AugmentCtx* ctx, void*) {
    float* base = static_cast<float*>(ctx->args[0]);
    std::printf("[mixin] boost: base %.1f -> ", *base);
    *base *= 1.5f;
    std::printf("%.1f\n", *base);
    std::fflush(stdout);
}

int main() {
    install_sigill_handler();
    augment_set_logger(test_logger);

    std::printf("[mixin] scale=%p dispatch=%p\n",
                reinterpret_cast<void*>(&augtest::scale),
                reinterpret_cast<void*>(&dispatch_scale));
    dump_bytes("scale-before", reinterpret_cast<void*>(&augtest::scale), 16);
    std::fflush(stdout);

    step("baseline call");
    float baseline = augtest::scale(40.0f, 2.0f);   // 80
    std::printf("[mixin] baseline=%.1f\n", baseline);
    std::fflush(stdout);

    step("register_ptr");
    augment_register_ptr("augtest::scale", reinterpret_cast<void*>(&dispatch_scale));

    AugmentRegOpts opts{};
    opts.augment_id = "boost";
    step("register before-hook");
    int ok = augment_register("augtest::scale", AUGMENT_PHASE_BEFORE, boost, nullptr, &opts);
    std::printf("[mixin] register ok=%d\n", ok);
    std::fflush(stdout);

    void* resolved = augment_resolve("augtest::scale");
    std::printf("[mixin] resolve(augtest::scale)=%p scale=%p match=%d\n",
                resolved,
                reinterpret_cast<void*>(&augtest::scale),
                resolved == reinterpret_cast<void*>(&augtest::scale));
    std::fflush(stdout);

    step("augment_self_test");
    int st = augment_self_test();
    std::printf("[mixin] self_test=%d\n", st);
    std::fflush(stdout);

    step("install_all");
    augment_install_all();
    dump_bytes("scale-after-hook", reinterpret_cast<void*>(&augtest::scale), 16);

    step("hooked call (enters patched scale -> dispatch)");
    float hooked = augtest::scale(40.0f, 2.0f);     // (40 * 1.5) * 2 = 120
    std::printf("[mixin] hooked=%.1f\n", hooked);
    std::fflush(stdout);

    int fails = 0;
    if (!ok)               { std::printf("FAIL register\n");                     ++fails; }
    if (baseline != 80.0f) { std::printf("FAIL baseline %.1f\n", baseline);      ++fails; }
    if (hooked != 120.0f)  { std::printf("FAIL hooked %.1f (want 120)\n", hooked); ++fails; }

    std::printf("baseline=%.1f hooked=%.1f\n", baseline, hooked);
    std::printf("%s\n", fails == 0 ? "mixin selftest PASSED" : "mixin selftest FAILED");
    std::fflush(stdout);
    return fails;
}
