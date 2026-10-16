// Augment Copyright (C) 2026 Liam
//
// Licensed under the MIT License.
// See LICENSE for details.

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
 * @brief Registers fn as a BEFORE-phase hook on sym at static-init time.
 *
 * @param sym Symbol to hook (unquoted identifier).
 * @param fn  Callable invoked as `fn(ctx)` when the hook fires.
 *
 * @note Intended for codegen. Always BEFORE phase, with no tag/contract handling.
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
 * @param index      Index into the tracked instances, or negative for the
 *                   most recently registered instance.
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

/**
 * @brief Signature for a log callback.
 *
 * @param tag Tag passed to the log function (for disambiguation).
 * @param msg Formatted message passed to the log function.
 */
using AugmentLogFn = void(*)(const char* tag, const char* msg);

/**
 * @brief Sets the log function called instead of fprintf.
 *
 * @param fn The AugmentLogFn to be called.
 */
AUGMENT_API void augment_set_logger(AugmentLogFn fn);

/**
 * @brief Invokes all hooks registered for a symbol.
 *
 * @param symbol Symbol name to invoke hooks for.
 * @param ctx    Context containing args, return slot, and state.
 */
AUGMENT_API void augment_invoke(const char* symbol, AugmentCtx* ctx);

/**
 * @brief Invokes BEFORE-phase hooks, returning the trampoline to the original.
 *
 * @param symbol Symbol name to invoke hooks for.
 * @param ctx    Context containing args and state.
 * @return       Function pointer to the original function, or nullptr if cancelled or not found.
 */
AUGMENT_API void* augment_before(const char* symbol, AugmentCtx* ctx);

/**
 * @brief Invokes AFTER-phase hooks.
 *
 * @param symbol Symbol name to invoke hooks for.
 * @param ctx    Context containing return value and state.
 */
AUGMENT_API void augment_after(const char* symbol, AugmentCtx* ctx);

/**
 * @brief Invokes BEFORE hooks and returns whether the original should run.
 *
 * @param symbol Symbol name to check hooks for.
 * @param ctx    Context containing args and state.
 * @return       1 if original should execute, 0 if cancelled.
 */
AUGMENT_API int augment_enter(const char* symbol, AugmentCtx* ctx);

/**
 * @brief Registers a hook callback for a symbol.
 *
 * @param symbol   Symbol name to hook.
 * @param phase    When to invoke the hook (before, after, or replace).
 * @param fn       Callback to invoke when the hook fires.
 * @param userdata Pointer passed through to the callback.
 * @param opts     Optional priority, tag, ID, and contract (nullable, all fields optional).
 * @return         1 on success, 0 on failure.
 */
AUGMENT_API int augment_register(
    const char*           symbol,
    AugmentPhase          phase,
    AugmentFn             fn,
    void*                 userdata,
    const AugmentRegOpts* opts
);

/**
 * @brief Registers the resolved address for a symbol.
 *
 * @param symbol     Symbol name.
 * @param target_ptr Address of the symbol.
 */
AUGMENT_API void augment_register_ptr(
    const char* symbol,
    void*       target_ptr
);

/**
 * @brief Hooks a function by address, bypassing symbol/manifest resolution
 *        and the chain/phase system entirely.
 *
 * @param target       Address of the function to hook.
 * @param replacement  Function to run instead of target.
 * @param out_original Receives a callable trampoline to the original (nullable).
 * @return             1 on success, 0 on failure (null args, already hooked, or backend failure).
 */
AUGMENT_API int augment_hook_ptr(void* target, void* replacement, void** out_original);

/** @brief Removes a hook installed by augment_hook_ptr. Returns 1 if removed. */
AUGMENT_API int augment_unhook_ptr(void* target);

/**
 * @brief Removes a registered hook by its augment_id.
 *
 * @param augment_id Unique identifier passed during registration.
 */
AUGMENT_API void augment_unregister(const char* augment_id);

/**
 * @brief Installs all pending hooks into their target functions.
 */
AUGMENT_API void augment_install_all(void);

/**
 * @brief Clears all registered hooks and resets internal state.
 */
AUGMENT_API void augment_clear(void);

/**
 * @brief Returns a JSON array of hooks registered for a symbol.
 *
 * @param symbol Symbol name to inspect.
 * @return       JSON string describing registered hooks, or "[]" if none.
 */
AUGMENT_API const char* augment_inspect(const char* symbol);

/**
 * @brief Resolves a symbol name to its address.
 *
 * @param symbol Symbol name to resolve.
 * @return       Address of the symbol, or nullptr if not found.
 */
AUGMENT_API void* augment_resolve(const char* symbol);

/**
 * @brief Runs internal consistency checks.
 *
 * @return 1 if all tests pass, 0 otherwise.
 */
AUGMENT_API int augment_self_test(void);

#if AUGMENT_FFI
/**
 * @brief Registers the type signature for a function.
 *
 * @param symbol    Symbol name.
 * @param is_member 1 if this is a member function, 0 otherwise.
 * @param rtype     Return type string.
 * @param atypes    Array of argument type strings.
 * @param nargs     Number of arguments.
 */
AUGMENT_API void augment_register_signature(const char* symbol, int is_member,
                                            const char* rtype, const char** atypes,
                                            unsigned nargs);

/**
 * @brief Registers the layout of a struct.
 *
 * @param name         Struct name.
 * @param member_kinds Array of member type strings.
 * @param n            Number of members.
 */
AUGMENT_API void augment_register_struct(const char* name, const char** member_kinds,
                                         unsigned n);

/**
 * @brief Loads function signatures from a file.
 *
 * @param path Path to the signature file.
 * @return     Number of signatures loaded (0 if file not found or empty).
 */
AUGMENT_API int augment_load_signatures(const char* path);

/**
 * @brief Returns the byte offset of a struct field.
 *
 * @param field Field name (qualified as "StructName.fieldName").
 * @return      Byte offset, or -1 if not found.
 */
AUGMENT_API int augment_field_offset(const char* field);

/**
 * @brief Creates a callable closure for a symbol.
 *
 * @param symbol Symbol name.
 * @return       Closure pointer, or nullptr on failure.
 */
AUGMENT_API void* augment_make_closure(const char* symbol);

/**
 * @brief Calls a function by symbol name.
 *
 * @param symbol         Symbol name to call.
 * @param args           Array of argument pointers.
 * @param nargs          Number of arguments.
 * @param ret_out        Buffer to store return value.
 * @param instance_index Index of the instance (for member functions, -1 for most recent).
 * @return               1 on success, 0 on failure.
 */
AUGMENT_API int augment_call(const char* symbol, void** args, unsigned nargs, void* ret_out, int instance_index = -1);
#else
inline void augment_register_signature(const char*, int, const char*, const char**, unsigned) {}
inline void augment_register_struct(const char*, const char**, unsigned) {}
inline int augment_load_signatures(const char*) { return 0; }
inline int augment_field_offset(const char*) { return -1; }
inline void* augment_make_closure(const char*) { return nullptr; }
inline int augment_call(const char*, void**, unsigned, void*, int = -1) { return 0; }
#endif

/**
 * @brief Describes a function parameter from debug metadata.
 */
typedef struct AugmentArg {
    const char* name; ///< Parameter name
    const char* kind; ///< Type name
    const char* view; ///< Display type (e.g., pointer-to, reference)
} AugmentArg;

/**
 * @brief Describes a struct field from debug metadata.
 */
typedef struct AugmentField {
    const char* name;     ///< Field name
    unsigned    offset;   ///< Byte offset from struct base
    const char* kind;     ///< Type name
    int         len;      ///< Array length (1 for non-arrays)
    const char* view;     ///< Display type
} AugmentField;

/**
 * @brief Loads debug metadata from a manifest file.
 *
 * @param path Path to the manifest file.
 * @return     Number of functions loaded, or 0 on failure.
 */
AUGMENT_API int augment_manifest_load(const char* path);

/**
 * @brief Returns the number of overloads for a flat (unmangled) function name.
 *
 * @param flat Flat function name.
 * @return     Overload count, or 0 if unknown.
 */
AUGMENT_API int augment_fn_count(const char* flat);

/**
 * @brief Returns the mangled name of the i-th overload.
 *
 * @param flat Flat function name.
 * @param i    Overload index.
 * @return     Mangled name, or nullptr if out of range.
 */
AUGMENT_API const char* augment_fn_mangled(const char* flat, int i);

/**
 * @brief Returns the source location of the i-th overload.
 *
 * @param flat Flat function name.
 * @param i    Overload index.
 * @return     Source location string, or empty string if unavailable.
 */
AUGMENT_API const char* augment_fn_loc(const char* flat, int i);

/**
 * @brief Resolves a flat name plus signature to a mangled name.
 *
 * @param flat Flat function name.
 * @param sig  Comma-separated type signature (e.g., "i32,f32").
 * @return     Mangled name, or nullptr if no match.
 */
AUGMENT_API const char* augment_resolve_sig(const char* flat, const char* sig);

/**
 * @brief Returns the parameter list for a function.
 *
 * @param mangled Mangled function name.
 * @param out     Receives pointer to parameter array.
 * @return        Parameter count, or 0 if unknown.
 */
AUGMENT_API int augment_fn_params(const char* mangled, const AugmentArg** out);

/**
 * @brief Returns the field list for a struct.
 *
 * @param name Struct name.
 * @param out  Receives pointer to field array.
 * @return     Field count, or 0 if unknown.
 */
AUGMENT_API int augment_struct_fields(const char* name, const AugmentField** out);

/**
 * @brief Describes an enum value from debug metadata.
 */
typedef struct AugmentEnumVal {
    const char* name;  ///< Enumerator name
    long long   value; ///< Enumerator value
} AugmentEnumVal;

/**
 * @brief Returns the enumerator list for an enum.
 *
 * @param name Enum name.
 * @param out  Receives pointer to enumerator array.
 * @return     Enumerator count, or 0 if unknown.
 */
AUGMENT_API int augment_enum_values(const char* name, const AugmentEnumVal** out);

/**
 * @brief Resolves a global variable name to its address and type.
 *
 * @param name     Global variable name.
 * @param kind_out Receives pointer to type name string.
 * @param addr_out Receives address of the global.
 * @return         1 if found, 0 otherwise.
 */
AUGMENT_API int augment_global_addr(const char* name, const char** kind_out, void** addr_out);

/**
 * @brief Returns the class/struct name for a member function.
 *
 * @param mangled Mangled function name.
 * @return        Class name, or empty string if not a member function.
 */
AUGMENT_API const char* augment_fn_self_view(const char* mangled);

/**
 * @brief Returns the return type of a function.
 *
 * @param mangled Mangled function name.
 * @return        Return type string, or nullptr if unknown.
 */
AUGMENT_API const char* augment_fn_ret(const char* mangled);

/**
 * @brief Reads a typed value from memory.
 *
 * @param base   Base address.
 * @param offset Byte offset from base.
 * @param kind   Type name.
 * @param out    Buffer to store the read value.
 */
AUGMENT_API void augment_mem_read(void* base, int offset, const char* kind, void* out);

/**
 * @brief Writes a typed value to memory.
 *
 * @param base   Base address.
 * @param offset Byte offset from base.
 * @param kind   Type name.
 * @param in     Pointer to the value to write.
 */
AUGMENT_API void augment_mem_write(void* base, int offset, const char* kind, const void* in);

/**
 * @brief Reads a null-terminated string from memory.
 *
 * @param base   Base address.
 * @param offset Byte offset from base.
 * @param cap    Maximum bytes to read (including null terminator).
 * @param out    Buffer to store the string.
 * @return       Number of bytes copied (excluding null terminator).
 */
AUGMENT_API int augment_mem_read_str(void* base, int offset, int cap, char* out);

/**
 * @brief Writes a null-terminated string to memory.
 *
 * @param base   Base address.
 * @param offset Byte offset from base.
 * @param cap    Maximum bytes to write (including null terminator).
 * @param s      String to write.
 */
AUGMENT_API void augment_mem_write_str(void* base, int offset, int cap, const char* s);

#ifdef __cplusplus
}
#endif

#endif /* AUGMENT_HPP */
