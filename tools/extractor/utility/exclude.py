def is_excluded(src: str, exclude_paths: tuple[str, ...]) -> bool:
    return any(frag in src for frag in exclude_paths)
