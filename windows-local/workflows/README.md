# Carey identity workflow references

The downloaded CivitAI JSON and local derivative described below remain in the
private on-machine library; this publication includes their provenance notes,
not a redistribution of those downloaded files.

The downloaded `civitai-ipadapter-faceid-sdxl-1144810.zip` is the small
`[SDXL, SD1.5] IPAdapter_FaceID workflow (Basic, Simple)` reference from
the CivitAI archive. Its SHA-256 is
`19576ef4c903edc2f8cc5c52aaaad060d54b46a7bf8b3158a65e6f7cd6e0a149`.
The unpacked workflow is kept here for manual import into ComfyUI.
`ByrdHouse_CivitAI_IPAdapterFaceID_SDXL_Carey.json` is the local import copy:
it points at the installed SDXL checkpoint and Carey portrait and includes the
Black/Carey identity prompt and negative guard.

It uses the same local pieces already installed on this PC:

- `IPAdapterInsightFaceLoader` with `buffalo_l`
- `IPAdapterFaceID` / `IPAdapterModelLoader`
- `CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors`
- the SDXL IPAdapter FaceID/PlusV2 weights under `D:\ByrdHouse\models`

The production Studio path uses the CivitAI-tested FaceID chain for new SDXL
scenes. The Identity Belt remains the correction and QA lane: ReActor →
ReActorMaskHelper → SAM, followed by InsightFace, 68-point outline, and
SegFormer hair/forehead scoring. It ranks direct, restored, smooth, and
multi-reference candidates and keeps every result in review. Run each output
through the belt before using it for animation.

The CivitAI workflow uses a generic checkpoint name and a sample input image.
The local import copy has those fields changed already. The belt's Studio
control accepts the resulting PNG filename.
