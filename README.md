# Lost & Found Website Prototype

A front-end prototype for a **campus lost-and-found matching platform**.

This project is a static website built with:
- HTML
- CSS
- JavaScript

It is designed to demonstrate the core product flow of a smart lost-and-found system, including:
- lost item listing
- found item listing
- item publishing form
- keyword search / filtering
- smart matching view
- notification center

---

## Project Structure

```bash
lostfound-website/
├── index.html
├── styles.css
├── script.js
└── README.md
```

---

## How to Run Locally

Since this is a static website, you do **not** need `npm install` or a backend server.

### Option 1: Open directly
Just double-click:

- `index.html`

### Option 2: Run with a simple local server
In terminal:

```bash
cd lostfound-website
python3 -m http.server 8000
```

Then open:

```text
http://localhost:8000
```

### Option 3: Open with VS Code Live Server
I personally use a VS Code extension called **Live Server** to open and preview this project.

Steps:
1. Open the folder in VS Code
2. Install the **Live Server** extension
3. Right-click `index.html`
4. Click **Open with Live Server**

---

## Features

### 1. Dashboard
Shows summary metrics such as:
- lost reports
- found reports
- pending matches
- notifications

### 2. Lost / Found Item Lists
Users can browse reports and filter them by category.

### 3. Publish Form
Users can simulate submitting a lost item or found item report.

### 4. Smart Matching
The system calculates possible matches based on:
- item category
- location similarity
- time proximity
- keyword overlap

### 5. Notification Center
Displays simulated alerts when possible matches are found.

---

## Notes

- This is a **prototype**, not a production-ready system.
- Data is currently stored in JavaScript memory only.
- There is no real backend, database, or authentication yet.
- Refreshing the page will reset the in-memory state.

---

## Current Limitation

Currently, the project is still missing an NLP feature that can search across different platforms to find related posts about a lost item from the website.

---

## Future Improvements

Possible next steps:
- add backend API
- connect to database
- support image upload
- implement real authentication
- improve matching algorithm
- add NLP to detect and retrieve related lost-item posts from different platforms
- deploy with Vercel / Netlify / Docker

---

## Author

Felix
