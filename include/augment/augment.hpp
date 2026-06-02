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

/* API */

AUGMENT_API int  augment_register(
    const char*           symbol,
    AugmentPhase          phase,
    AugmentFn             fn,
    void*                 userdata,
    const AugmentRegOpts* opts // nullable, all fields optional
);

AUGMENT_API void augment_unregister_augment(const char* augment_id);
AUGMENT_API void augment_install_all(void);
AUGMENT_API void augment_clear(void);
AUGMENT_API const char* augment_inspect(const char* symbol);

#ifdef __cplusplus
}
#endif

#endif /* AUGMENT_HPP */