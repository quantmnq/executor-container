# Third-party components

Original Follow Executor files are GPL-3.0-or-later; that does not replace
third-party licenses. This release preserves upstream notices and provides
matching source as described in [SOURCE](docs/SOURCE.md).

| Component | Version / source | License and notices |
| --- | --- | --- |
| Official IBKR Python TWS API | 10.50.2; checksum-pinned official archive in `deploy/executor-container/install-api.py` | GPL-3.0-or-later; [license](licenses/IBKR-API-LICENSE.txt), [notice](licenses/IBKR-API-NOTICE.txt). Unmodified API source is retained in the dependency source archive. |
| cryptography, cffi, pycparser, protobuf | Exact versions and wheel hashes in `deploy/executor-container/requirements.lock` | Upstream licenses remain in installed distribution metadata and the dependency source archive. cryptography includes its Apache/BSD notices and notices for bundled OpenSSL/Rust components. |
| CPython and pip | Exact runtime versions in the dependency archive's `INVENTORY.json` | PSF/Python historical notices and pip's MIT/vendored notices remain with their sources and installed files. |
| Debian base-image packages | Exact binary-to-source mapping in `INVENTORY.json` | Copyright notices under `/usr/share/doc/*/copyright` and `/usr/share/common-licenses` in the image, also retained with the matching Debian sources and patches. |
| gnzsnz/ib-gateway-docker scripts | Immutable upstream image digest in `src/follow_executor/gateway_docker.py` | [MIT notice](licenses/ib-gateway-docker-MIT.txt). This is the wrapper project's license, not a license grant for IB Gateway. |
| IB Gateway and IBC | Downloaded separately by the customer's installer | The upstream downloads retain their own terms/notices. The customer kit does not contain the Gateway image, Gateway installer or IBC binaries. |

The image keeps its upstream Python package license files. We additionally install
IBKR's archive-level LICENSE and NOTICE under `/usr/share/licenses/ibapi`, and
Follow Executor's LICENSE/NOTICE under `/usr/share/licenses/follow-executor`.

The dependency source archive contains the original IBKR ZIP, installed Python
package source distributions, CPython source, Debian source packages and their
copyright notices. Each file is checksummed. Build dependencies are pinned in
`build-requirements.lock`; their licenses remain with upstream distributions.

IBKR/Discord screenshots illustrate their user interfaces. Product names, logos
and interface elements remain the respective owners' material; these notices do
not claim to relicense them or imply endorsement.
