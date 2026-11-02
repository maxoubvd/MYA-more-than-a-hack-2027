# MYA frozen model assets

`model.json` contains only learned external-data parameters, preprocessing,
observation-context parameters, the static temporal prior and the final settings.
It contains no competition coordinates, images, framewise labels or predictions.
`manifest.json` freezes the model, source/configuration fingerprints and exact
expected CSV SHA256. Source fingerprints normalize UTF-8 BOM/CRLF; model hashes
use canonical JSON. This is an integrity/reproduction record, not a signature
from a trusted third party.

Training source: Bassek et al. (2025), DFL / IDSSE / Sportec Solutions,
Figshare article 28196177 version 1, DOI 10.6084/m9.figshare.28196177.v1.
The dataset is CC BY 4.0. Attribution and upstream metadata are recorded in
`docs/sources.json` and `configs/dfl_manifest.json`. The provider's BallStatus and
BallPossession labels were used on the four registered training matches only.

The small JSON weights are shipped with the source repository. Reproducing the
submission does not require downloading the external training dataset. The
competition data is private and must be supplied separately by an authorized
participant. No competition labels were used to fit or select these parameters.

See `docs/DELIVERY.md` and `MYA.md` for installation, execution and limitations.
