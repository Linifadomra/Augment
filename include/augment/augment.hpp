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

#pragma once

#ifndef AUGMENT_HPP
#define AUGMENT_HPP

#include <stdint.h>
#include "augment/augment_export.h"

#ifdef __cplusplus
extern "C" {
#endif

/* TYPES */

typedef enum AugmentPhase {
    AUGMENT_PHASE_BEFORE  = 0,
    AUGMENT_PHASE_AFTER   = 1,
    AUGMENT_PHASE_REPLACE = 2,
} AugmentPhase;

typedef struct AugmentCtx {
    void*    self;      // this pointer
    void**   args;      // argument array, index 0 = first param
    void*    ret;       // return value slot
    int      cancelled; // set nonzero in before to skip original
    void*    user;      // internal, do not touch
    int      arg_count; // number of arguments
} AugmentCtx;

typedef void (*AugmentFn)(AugmentCtx* ctx, void* userdata);

typedef struct AugmentContract {
    const char* const* affects;  int n_affects;
    const char* const* reads;    int n_reads;
    const char* const* writes;   int n_writes;
} AugmentContract;

typedef struct AugmentRegOpts {
    int                priority;
    const char*        tag;
    const char*        augment_id;
    AugmentContract    contract;
} AugmentRegOpts;

#define AUGMENT_HOOK(sym, fn)                                           \
    static struct _AugmentAutoHook_##sym {                              \
        _AugmentAutoHook_##sym() {                                      \
            static const auto _fn = fn;                                 \
            augment_register(                                           \
                #sym,                                                   \
                AUGMENT_PHASE_BEFORE,                                   \
                [](AugmentCtx* ctx, void*) { _fn(ctx); },               \
                nullptr, nullptr);                                      \
        }                                                               \
    } _augment_autohook_instance_##sym

AUGMENT_API void  augment_register_instance(const char* class_name, void* ptr);
AUGMENT_API void  augment_unregister_instance(const char* class_name, void* ptr);
AUGMENT_API void* augment_get_instance(const char* class_name, int index);
AUGMENT_API int augment_instance_count(const char* class_name);

/* API */

using AugmentLogFn = void(*)(const char* tag, const char* msg);
AUGMENT_API void augment_set_logger(AugmentLogFn fn);

AUGMENT_API void augment_invoke(const char* symbol, AugmentCtx* ctx);
AUGMENT_API void* augment_before(const char* symbol, AugmentCtx* ctx);
AUGMENT_API void augment_after(const char* symbol, AugmentCtx* ctx);
AUGMENT_API int augment_enter(const char* symbol, AugmentCtx* ctx);
AUGMENT_API int augment_register(
    const char*           symbol,
    AugmentPhase          phase,
    AugmentFn             fn,
    void*                 userdata,
    const AugmentRegOpts* opts // nullable, all fields optional
);
AUGMENT_API void augment_register_ptr(
    const char* symbol,
    void*       target_ptr
);

AUGMENT_API void augment_unregister(const char* augment_id);
AUGMENT_API void augment_install_all(void);
AUGMENT_API void augment_clear(void);
AUGMENT_API const char* augment_inspect(const char* symbol);
AUGMENT_API void* augment_resolve(const char* symbol);
AUGMENT_API int augment_self_test(void);

#if AUGMENT_FFI
AUGMENT_API void augment_register_signature(const char* symbol, int is_member,
                                            const char* rtype, const char** atypes,
                                            unsigned nargs);
AUGMENT_API void augment_register_struct(const char* name, const char** member_kinds,
                                         unsigned n);
AUGMENT_API int augment_load_signatures(const char* path);
AUGMENT_API int augment_field_offset(const char* field);
AUGMENT_API void* augment_make_closure(const char* symbol);
AUGMENT_API void augment_call(const char* symbol, void** args, unsigned nargs, int instance_index = -1);
#else
inline void augment_register_signature(const char*, int, const char*, const char**, unsigned) {}
inline void augment_register_struct(const char*, const char**, unsigned) {}
inline int augment_load_signatures(const char*) { return 0; }
inline int augment_field_offset(const char*) { return -1; }
inline void* augment_make_closure(const char*) { return nullptr; }
inline void augment_call(const char*, void**, unsigned, int) {}
#endif

typedef struct AugmentArg   { const char* name; const char* kind; const char* view; } AugmentArg;
typedef struct AugmentField { const char* name; unsigned offset; const char* kind; int len; const char* view; } AugmentField;

AUGMENT_API int augment_manifest_load(const char* path);

AUGMENT_API int augment_fn_count(const char* flat);
AUGMENT_API const char* augment_fn_mangled(const char* flat, int i);
AUGMENT_API const char* augment_fn_loc(const char* flat, int i);
AUGMENT_API const char* augment_resolve_at(const char* flat, const char* file_substr);
AUGMENT_API const char* augment_resolve_sig(const char* flat, const char* sig);

AUGMENT_API int augment_fn_params(const char* mangled, const AugmentArg** out);
AUGMENT_API int augment_struct_fields(const char* name, const AugmentField** out);
typedef struct AugmentEnumVal { const char* name; long long value; } AugmentEnumVal;
AUGMENT_API int augment_enum_values(const char* name, const AugmentEnumVal** out);
AUGMENT_API int augment_global_addr(const char* name, const char** kind_out, void** addr_out);

AUGMENT_API const char* augment_fn_self_view(const char* mangled);
AUGMENT_API const char* augment_fn_ret(const char* mangled);

AUGMENT_API void augment_mem_read(void* base, int offset, const char* kind, void* out);
AUGMENT_API void augment_mem_write(void* base, int offset, const char* kind, const void* in);
AUGMENT_API int augment_mem_read_str(void* base, int offset, int cap, char* out);
AUGMENT_API void augment_mem_write_str(void* base, int offset, int cap, const char* s);

#ifdef __cplusplus
}
#endif

#endif /* AUGMENT_HPP */