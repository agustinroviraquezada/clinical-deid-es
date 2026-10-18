---
paths:
  - "src/clinical_deid/api/static/**"
---

# Frontend rules

- Plain HTML + JavaScript, no framework and no CDN dependencies.
- UI text in English.
- User or API data always through `textContent` or by creating nodes; **never** `innerHTML`.
- The privacy notice must be visible before processing.
- Accessible: labelled form fields, sufficient contrast, keyboard navigable.
- Show the MEDDOCAN attribution next to the examples.
