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

/**
 * @brief Function hook phase enum
 */
typedef enum AugmentPhase {
    /**
     * @brief Hook is invoked before the original function body executes.
     *
     * The original function still runs afterward.
     */
    AUGMENT_PHASE_BEFORE = 0,

    /**
     * @brief Hook is invoked after the original function executes but before returning.
     *
     * Useful for inspecting or modifying the return value.
     */
    AUGMENT_PHASE_AFTER = 1,

    /**
     * @brief Hook completely replaces the original function.
     *
     * The original function is never called.
     */
    AUGMENT_PHASE_REPLACE = 2,
} AugmentPhase;

/**
 * @brief Context passed to a hooked function's callback
 */
typedef struct AugmentCtx {
    void*    self;      ///< this pointer
    void**   args;      ///< argument array, index 0 = first param
    void*    ret;       ///< return value slot
    int      cancelled; ///< set nonzero in before to skip original
    void*    user;      ///< internal, do not touch
    int      arg_count; ///< number of arguments
} AugmentCtx;

/**
 * @brief Signature for a hook callback function.
 *
 * @param ctx      Context for the current invocation (args, return slot, etc.)
 * @param userdata User-supplied pointer passed through from registration.
 */
typedef void (*AugmentFn)(AugmentCtx* ctx, void* userdata);

/**
 * @brief Declares what a hook touches, for automated conflict detection.
 *
 * Hooks whose contracts overlap (e.g. one writes what another reads/affects)
 * can be flagged instead of colliding silently.
 */
typedef struct AugmentContract {
    const char* const* affects;  ///< Symbols/fields this hook affects (side effects)
    int                n_affects;///< Number of entries in affects

    const char* const* reads;    ///< Symbols/fields this hook reads
    int                n_reads;  ///< Number of entries in reads

    const char* const* writes;   ///< Symbols/fields this hook writes
    int                n_writes; ///< Number of entries in writes
} AugmentContract;

/**
 * @brief Options used when registering a hook.
 */
typedef struct AugmentRegOpts {
    int             priority;   ///< Execution order relative to other hooks (lower runs first)
    const char*     tag;        ///< Human-readable label for logs / debug
    const char*     augment_id; ///< Unique identifier for this hook registration
    AugmentContract contract;   ///< Declared read/write/affects surface, for conflict detection
} AugmentRegOpts;

/**
 * @def AUGMENT_HOOK(sym, fn)
 * @brief Registers @p fn as a BEFORE-phase hook on @p sym at static-init time.
 *
 * Declares a file-scope struct whose constructor runs before main(),
 * calling augment_register() to install @p fn as a hook. This lets a hook
 * be registered just by writing a single macro invocation at file scope,
 * with no explicit init function required.
 *
 * @param sym Symbol to hook (unquoted identifier; stringified internally).
 * @param fn  Callable invoked as `fn(ctx)` when the hook fires.
 *
 * @note Currently unused directly by hand-written code. Intended to be
 *       emitted by codegen from source annotations (e.g. an attribute or
 *       comment marker on a function), rather than written manually.
 * @note Always registers with phase AUGMENT_PHASE_BEFORE and no tag/contract.
 *       If codegen needs to control phase or contract, this macro will need
 *       additional parameters or sibling macros (e.g. AUGMENT_HOOK_AFTER).
 */
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

/**
 * @brief Registers a live instance pointer under a class name for later lookup.
 *
 * Used so that member-function calls made via augment_call() can resolve
 * a 'this' pointer without the caller needing to track instances manually.
 * Duplicate pointers already tracked under @p class_name are ignored.
 *
 * @param class_name Name identifying the instance's class (matches self_view).
 * @param ptr        Instance pointer to track.
 */
AUGMENT_API void  augment_register_instance(const char* class_name, void* ptr);

/**
 * @brief Removes a previously registered instance pointer.
 *
 * No-op if @p class_name is unknown or @p ptr was never registered.
 *
 * @param class_name Name identifying the instance's class.
 * @param ptr        Instance pointer to stop tracking.
 */
AUGMENT_API void  augment_unregister_instance(const char* class_name, void* ptr);

/**
 * @brief Retrieves a tracked instance pointer by index.
 *
 * @param class_name Name identifying the instance's class.
 * @param index       Index into the tracked instances, or negative for the
 *                     most recently registered instance.
 * @return Instance pointer, or nullptr if @p class_name is unknown, has no
 *         tracked instances, or @p index is out of range.
 */
AUGMENT_API void* augment_get_instance(const char* class_name, int index);

/**
 * @brief Returns the number of instances currently tracked for a class.
 *
 * @param class_name Name identifying the instance's class.
 * @return Count of tracked instances, or 0 if @p class_name is unknown.
 */
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
AUGMENT_API int augment_call(const char* symbol, void** args, unsigned nargs, void* ret_out, int instance_index = -1);
#else
inline void augment_register_signature(const char*, int, const char*, const char**, unsigned) {}
inline void augment_register_struct(const char*, const char**, unsigned) {}
inline int augment_load_signatures(const char*) { return 0; }
inline int augment_field_offset(const char*) { return -1; }
inline void* augment_make_closure(const char*) { return nullptr; }
inline int augment_call(const char*, void**, unsigned, void*, int = -1) { return 0; }
#endif

typedef struct AugmentArg   { const char* name; const char* kind; const char* view; } AugmentArg;
typedef struct AugmentField { const char* name; unsigned offset; const char* kind; int len; const char* view; } AugmentField;

AUGMENT_API int augment_manifest_load(const char* path);

AUGMENT_API int augment_fn_count(const char* flat);
AUGMENT_API const char* augment_fn_mangled(const char* flat, int i);
AUGMENT_API const char* augment_fn_loc(const char* flat, int i);
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