if __package__:
    from .launcher import main
else:  # Preserve direct source invocation: python /path/to/__main__.py.
    from launcher import main

if __name__ == "__main__":
    raise SystemExit(main())
