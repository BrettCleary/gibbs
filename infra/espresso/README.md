# Quantum ESPRESSO container

The `espresso` engine shells out to `pw.x`. This directory pins that binary to a
container image so the science doesn't depend on whatever the host distro ships.

## Why not the distro package

Ubuntu 24.04's `quantum-espresso` 6.7-2build4 aborts on **every** pseudopotential:

```
*** buffer overflow detected ***: terminated
```

QE's `md5_from_file()` formats a 16-byte digest with `sprintf(&md5[i*2], "%02x")`
into a 32-char buffer; the last write puts two characters plus a NUL one byte
past the end. Ubuntu 24.04 builds with `_FORTIFY_SOURCE=3`, where glibc catches
the off-by-one and aborts. The overflow is real on every distro — older ones just
didn't detect it. It fires while reading the pseudopotential, before the first
SCF iteration, so no engine setting can work around it and `espresso.pwo` is
left empty (the abort message goes to `espresso.err`).

Noble ships only 6.7, so `apt upgrade` does not help.

## Build

```bash
docker build -t alloylab-qe:7.5 infra/espresso
```

QE comes from conda-forge, which tracks upstream releases. To move version, bump
`QE_VERSION` and the image tag together:

```bash
docker build --build-arg QE_VERSION=7.5 -t alloylab-qe:7.5 infra/espresso
```

## Use

`pw.x` in this directory is a shim that runs the image with the calculation
workdir and the pseudopotential directory bind-mounted at their host paths, as
the invoking user. Point the API at it:

```bash
export ALLOYLAB_PW_COMMAND=$PWD/infra/espresso/pw.x
export ALLOYLAB_PSEUDO_DIR=$PWD/infra/pseudopotentials
```

`ALLOYLAB_QE_IMAGE` overrides the image tag; `OMP_NUM_THREADS` is passed through.
The shim reads `pseudo_dir` back out of the `.pwi` when `ALLOYLAB_PSEUDO_DIR`
isn't set, so the absolute path ASE writes into the input always resolves inside
the container.

Verify:

```bash
ALLOYLAB_PW_COMMAND=$PWD/infra/espresso/pw.x \
ALLOYLAB_PSEUDO_DIR=$PWD/infra/pseudopotentials \
  uv run --package alloyscience pytest packages/science/tests/test_calculators.py -q
```
