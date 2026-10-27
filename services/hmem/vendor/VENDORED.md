# Vendored: Meterless H-MEM reference

`hmem/` is a byte-identical copy of files from the official Meterless repository. Nothing in it is modified; our code lives one level up (`../server.ts`).

| | |
|---|---|
| Source | `github.com/Meterless/Meterless`, path `engines/hmem` |
| Commit | `1742dec56a66e58eef9dda2d2b865823758ca8cd` |
| License | Apache-2.0 (`hmem/LICENSE`) |
| Copied | `reference/src/*.ts`, `reference/package.json`, `reference/package-lock.json`, `reference/tsconfig.json`, `conformance/runner.ts`, `conformance/README.md`, `conformance/vectors/vectors.json`, `LICENSE` |
| Not copied | reference tests, docs, demos, examples, evals, workshops |

`reference/` and `conformance/` stay siblings so the runner's default paths work. The image build runs the conformance suite against `reference/src/index.ts`, the module the service serves.

## Checksums (SHA-256)

Verify by saving the block below to a file and running `sha256sum -c <file>` in `services/hmem/vendor`, or compare against `git show 1742dec:engines/hmem/<path>` in a Meterless checkout.

```
cf44fd4d3c9a8af0c46157bb015dead8d4ccb2d000c2358e7da1e4cecfbc4c39  hmem/conformance/README.md
d6724860761c4846a0bce3080d25115bcb0ba1d9d0d2e933438f5683a7a9b7c5  hmem/conformance/runner.ts
10afb5a07233466576ba6feb0d88408488909ba2721ee9157fdb932132917029  hmem/conformance/vectors/vectors.json
63e29fc8231b53757a77fbc371071c91d768621efa1e68b1d9ff8d1bb7c4a0ef  hmem/LICENSE
982b032b671667f6c3c2f857ab0791a8f78f9574957410dcd1d0a65119cde18d  hmem/reference/package.json
62bb56c945cd18e5aa4cfe74eb63659cb46b66e6b4a2c79c689d625775ca8b65  hmem/reference/package-lock.json
432e8b86ed0b5883d435e5ab4a12160d1f40d194cbdb4c119d3b710cbb0301a3  hmem/reference/src/conflictDetection.ts
d12594d667ec068690c6b81e020cd62ade91671316a1ab9b529259304aceb009  hmem/reference/src/dreaming.ts
89433327ee1075a8049bc8518cdf5cabf51ad67802e192266841cdee727b6d10  hmem/reference/src/embeddings.ts
9c481889afcdd70086d3bb3470842fa2330215e4d7760d826d103accdf8c1cdf  hmem/reference/src/index.ts
6072693d654ea1c34a9adbf6ce80101eeb1eeb56273d264f6ceb4859ffde6562  hmem/reference/src/memoryMining.ts
4fe120b1b64fe7225b9b28fda59514c114de9e885d22c5bf0aa035788b6d629d  hmem/reference/src/memoryRetrieval.ts
a1eac8de8c0fde0e503e1212f3cb98295a661c2a8bad93ad82e51985885e6fd0  hmem/reference/src/memoryStore.ts
3ce0d4f3233d0ad7c133a2cbaf39b6122467022e0aa378a160a0d463e2264cef  hmem/reference/src/sleepCycle.ts
263253dd3342c488ce773d7e728d77aec983c1833873602b59ce1a6c7999e20e  hmem/reference/src/trustLedger.ts
becb504870a67646a20a421ffe04d8732db63418393423d2186c074b182f54c7  hmem/reference/src/types.ts
a0e236840f54f788dec6c2a56a84b7cd737bac932848fd8808dc20f94e49d4d4  hmem/reference/tsconfig.json
```
