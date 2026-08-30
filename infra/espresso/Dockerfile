# Quantum ESPRESSO for the `espresso` engine.
#
# Ubuntu's quantum-espresso 6.7 package aborts on every pseudopotential:
# md5_from_file() writes 33 bytes into a 32-byte buffer, which _FORTIFY_SOURCE=3
# (Ubuntu 24.04 default) turns into "*** buffer overflow detected ***".
# conda-forge ships a current, correctly built QE, pinned here.
FROM mambaorg/micromamba:2.3.2

ARG QE_VERSION=7.5
RUN micromamba install -y -n base -c conda-forge "qe=${QE_VERSION}" \
    && micromamba clean --all --yes

ENV PATH=/opt/conda/bin:$PATH
