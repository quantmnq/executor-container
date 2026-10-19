# GPL customer releases

English | [简体中文](RELEASING.zh-CN.md)

The owner has selected GPL-3.0-or-later for the customer executor. The signal
service and provider strategy remain separate and private. Publish the reviewed
public export, never this VM's entire checkout, Git history, home directory,
release evidence, credentials or journal. [Source/build details](SOURCE.md).

## Build and validate

Version 0.1.11 adds source delivery and notices to the credential-isolated 0.1.10
runtime. Use CPython 3.12 on Ubuntu 24.04 ARM64 with Docker. Set the version in
`pyproject.toml`, the default image tag in the launcher/tests, and bilingual
versioned examples together. Old release archives are immutable.

```bash
.venv/bin/ruff check .
bash -n follow follow-container follow-stack install.sh deploy/install-bytecode.sh scripts/*.sh
.venv/bin/python -m unittest discover -s tests -v
python3.12 scripts/build-executor-container.py
python3.12 scripts/test-executor-container.py
python3.12 scripts/test-executor-isolation.py
python3.12 scripts/collect-third-party-source.py --image follow-executor:0.1.11
python3.12 scripts/build-container-kit.py --build dist/executor-container/BUILD.json --third-party dist/third-party/SOURCES.json
python3.12 scripts/build-source.py --output dist/source --export dist/public-repository
```

The source export reads only the explicit `deploy/public-files.txt` allowlist.
It excludes Git history, local settings, `vendor/`, `dist/`, private release
handoffs and all provider services. Add new application modules to that allowlist;
the builder refuses to omit a module. Review every newly allowlisted file.
Never use `git add .` in the working VM checkout to prepare a public repository.

The image build uses a small allowlisted context. It adds the application's
license metadata and preserves the official IBKR archive's LICENSE, NOTICE and
THIRD_PARTY_LICENSES in the final image. Do not strip dependencies' own notices.
The dependency collector uses a disposable container, mounts only its output
folder, and downloads exact Debian source versions plus Python/API sources.
It does not log into IBKR, access a relay, or alter host services.

The combined-kit builder refuses a stale image context, mismatched wheel, wrong
architecture, changed dependency archive or mismatched installed dependency
versions. Each kit includes its matching application source archive. The wheel
and source must be built from the same reviewed tree. Test from the extracted
source as well as the working checkout, and compare the rebuilt wheel hash.

Run real Docker isolation/lifecycle checks with synthetic fixtures, then repeat
isolation using the final kit's launcher. Verify all archive checksums, matching
source hashes, English/Chinese guide links and private-state preservation.
Automated tests do not establish profitability or validate an unobserved login.

## Publish on the new GitHub account

Create a new **public**, empty repository on the owner's chosen account. The
export already contains LICENSE, README and `.gitignore`; do not generate
conflicting versions on GitHub. Upload only `dist/public-repository/` contents.
The new repository starts with this reviewed source, without the working VM's
old Git history. GitHub Desktop can publish that exported folder; it does not
need access to this VM's secrets. No repository URL is assumed by the code.

Create a release/tag matching version 0.1.11 and attach all of these from the
reviewed release output:

- `follow-stack-0.1.11-ubuntu24.04-arm64-cp312.tar.gz`
- Its `.tar.gz.sha256` checksum file
- `follow-executor-0.1.11-source.tar.gz` (also included inside the kit)
- `follow-executor-0.1.11-dependencies.tar.gz`
- `SHA256SUMS` covering these release assets

Offer the source downloads beside the binary download at no additional charge.
Do not condition access to source for an existing recipient on renewing the
signal subscription. Do not add a software NDA, no-modification or no-resale
restriction that contradicts the GPL. Service access remains separately
authorized; source publication does not supply a relay token or strategy code.

Retain every published binary and its exact source/dependency archives, license
notices and hashes. If changing download hosts, preserve source availability.
A checksum proves integrity only when obtained through a trusted channel.

The dependency source archive is larger than the installer and is optional for
normal installation. It belongs in GitHub Release assets, not the Git source
tree. Review the release's source and checksum links before inviting customers.
Supply personal relay tokens privately and confirm the provider fingerprint.

## Rollout and maintenance

Use the English/Chinese beginner setup guides. Start with two or three paper
customers, including first-time terminal users. Their own readiness checks must
pass; setup never starts trading. Review mode, instrument and size before their
explicit start. An AI assistant is optional. Existing installations require a
stopped-and-flat migration that preserves their journals and regenerates the
service to obtain the credential-isolation mounts. A new image alone is not enough.

Publication does not deploy to the running pilot or authorize live trading.
The native Gateway path remains available for existing installations; AMD64 is
not a supported customer target. Changing the upstream Gateway pin requires its
own login/recovery acceptance, independent of source-release packaging.
