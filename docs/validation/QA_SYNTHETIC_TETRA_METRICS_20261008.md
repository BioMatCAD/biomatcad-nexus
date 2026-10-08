# BioMatCAD — E2E synthetic tetrahedron QA

Status: RESEARCH ONLY / OPEN ISSUE (2026-10-08).

The E2E seed `apps/api/scripts/seed_e2e_user.py` emits a tetrahedron with four triangular facets, edge intercepts at 10 mm, and a 0–10 mm bounding box. Its `_expected_metrics()` currently reports 100 triangles, 168 unique vertices, 400 mm3 volume and 950.5 mm2 surface area. These values are inconsistent with the mesh.

Expected geometric values for the ideal tetrahedron: 4 triangles; 4 unique vertices; volume 1000/6 = 166.6666667 mm3; area 150 + 50*sqrt(3) = 236.6025404 mm2. A solid tetrahedron has no internal porosity (0%), not the reported 60%. Two facet normals also disagree with the winding and must be checked before treating the mesh as an oriented watertight surface.

This is a synthetic fixture, not a real Geometry Worker result. Do not represent the fixture as scientifically verified. Correct the fixture and adjust `apps/web/e2e/vertical.spec.ts` expectations together; preserve the separate geometry-worker golden tests.

Evidence: static review of the source at `c0028f0af57cf1896ec75adaaa3999d3f82bca27`; no runtime geometry validation claimed.
