#!/usr/bin/env bash
# pw.x shim: runs Quantum ESPRESSO in the pinned alloylab-qe container.
#
# ASE invokes this as `<command> -in espresso.pwi` with cwd set to the
# calculation's workdir, capturing stdout/stderr into espresso.pwo/.err. We
# bind-mount the workdir and the pseudopotential directory at their host paths
# so the absolute `pseudo_dir` written into the .pwi resolves inside the
# container, and run as the invoking user so artifacts aren't owned by root.
#
# Point the API at this file:  export ALLOYLAB_PW_COMMAND=$PWD/infra/espresso/pw.x
set -euo pipefail

IMAGE="${ALLOYLAB_QE_IMAGE:-alloylab-qe:7.5}"

# pseudo_dir: explicit override, else read it back out of the input file.
pseudo_dir="${ALLOYLAB_PSEUDO_DIR:-}"
if [[ -z "$pseudo_dir" ]]; then
  for ((i = 1; i <= $#; i++)); do
    if [[ "${!i}" == "-in" || "${!i}" == "-inp" || "${!i}" == "-input" ]]; then
      j=$((i + 1))
      if [[ $j -le $# && -f "${!j}" ]]; then
        pseudo_dir=$(sed -n "s/.*pseudo_dir[[:space:]]*=[[:space:]]*['\"]\([^'\"]*\)['\"].*/\1/p" "${!j}" | head -1)
      fi
      break
    fi
  done
fi

mounts=(-v "$PWD:$PWD")
if [[ -n "$pseudo_dir" && -d "$pseudo_dir" ]]; then
  pseudo_dir=$(cd "$pseudo_dir" && pwd -P)
  # Skip if already covered by the workdir mount.
  [[ "$pseudo_dir" == "$PWD"/* || "$pseudo_dir" == "$PWD" ]] || mounts+=(-v "$pseudo_dir:$pseudo_dir:ro")
fi

exec docker run --rm --user "$(id -u):$(id -g)" \
  "${mounts[@]}" -w "$PWD" \
  -e OMP_NUM_THREADS="${OMP_NUM_THREADS:-4}" \
  "$IMAGE" pw.x "$@"
