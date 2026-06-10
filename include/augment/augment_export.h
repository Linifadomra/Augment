
#ifndef AUGMENT_API_H
#define AUGMENT_API_H

#ifdef AUGMENT_STATIC_DEFINE
#  define AUGMENT_API
#  define AUGMENT_NO_EXPORT
#else
#  ifndef AUGMENT_API
#    ifdef augment_EXPORTS
        /* We are building this library */
#      define AUGMENT_API 
#    else
        /* We are using this library */
#      define AUGMENT_API 
#    endif
#  endif

#  ifndef AUGMENT_NO_EXPORT
#    define AUGMENT_NO_EXPORT 
#  endif
#endif

#ifndef AUGMENT_DEPRECATED
#  define AUGMENT_DEPRECATED __declspec(deprecated)
#endif

#ifndef AUGMENT_DEPRECATED_EXPORT
#  define AUGMENT_DEPRECATED_EXPORT AUGMENT_API AUGMENT_DEPRECATED
#endif

#ifndef AUGMENT_DEPRECATED_NO_EXPORT
#  define AUGMENT_DEPRECATED_NO_EXPORT AUGMENT_NO_EXPORT AUGMENT_DEPRECATED
#endif

/* NOLINTNEXTLINE(readability-avoid-unconditional-preprocessor-if) */
#if 0 /* DEFINE_NO_DEPRECATED */
#  ifndef AUGMENT_NO_DEPRECATED
#    define AUGMENT_NO_DEPRECATED
#  endif
#endif

#endif /* AUGMENT_API_H */
