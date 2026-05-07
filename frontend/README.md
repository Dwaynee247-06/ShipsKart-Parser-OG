# ShipsKart Parser — Frontend Test Client

A lightweight static frontend for testing the ShipsKart Parser API.  
No build step required. Just open `index.html` in a browser.

## File Structure

```
frontend/
├── index.html   # Main UI — upload, results, summary
├── style.css    # All styles (light + dark mode, design tokens)
├── app.js       # All logic (file upload, API calls, rendering, filters)
└── README.md    # This file
```

## How to Use

1. Make sure the backend is running:
   ```
   uvicorn app.main:app --reload
   ```
2. Open `index.html` directly in a browser (no server needed for the frontend).
3. The API base URL defaults to `http://localhost:8000` — change it in the input if needed.
4. Upload an Excel / Word / PDF file and click **Parse & Match**.

## Features

- Drag-and-drop or click-to-browse file upload
- Live API health badge (auto-checks on load and URL change)
- Configurable `top_n` matches per item
- Summary tiles: total / strong (>=80%) / possible (50-79%) / unmatched
- Expandable per-item rows showing all match candidates with score bars
- Filter by item name (search box) and score tier (dropdown)
- Download full JSON response
- Light / dark mode toggle
