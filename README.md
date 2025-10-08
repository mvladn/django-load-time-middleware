# Django Load Time Middleware

A lightweight Django middleware that measures request performance — showing server, database, and client load times through HTTP headers and an optional floating badge.  
It is designed to be safe for production environments and has negligible performance impact.

---

## Why

The popular [django-debug-toolbar](https://github.com/jazzband/django-debug-toolbar) provides extensive insights for development but adds significant overhead.  
This middleware was created as a lightweight alternative suitable for production use, offering key timing metrics without slowing down requests.

---

## Compatibility

- Tested on **Django 5.0**, should work with **Django 2.2 or higher**
- Requires **Python 3.7 or higher**

---

## Features

- Adds `Server-Timing` and `X-LoadTime-*` headers  
- Optionally injects a floating badge on HTML responses  
- Measures:
  - Total server time  
  - Database time and query count  
  - Application (non-DB) time  
  - Client-side load time (measured in JavaScript)  
- Works with multiple databases  
- No external dependencies

---

## Installation

1. Copy the entire `load_time_middleware` folder into your Django project (next to your apps). 
2. In `settings.py`, enable it conditionally:

```python
DISPLAY_LOAD_TIMES = DEBUG  # or use an environment variable

if DISPLAY_LOAD_TIMES:
    MIDDLEWARE.insert(0, "load_time_middleware.middleware.LoadTimeMiddleware")
```

Reload any page to see timing headers and, for HTML responses, the load time badge in the bottom-right corner.

---

## Example Headers

```
Server-Timing: total;dur=215.3, db;dur=87.6, app;dur=127.7
X-LoadTime-TotalMs: 215.3
X-LoadTime-DatabaseMs: 87.6
X-LoadTime-NoOfDatabaseQueries: 12
X-LoadTime-AppMs: 127.7
```

---

## The Badge

On HTML pages, a small floating badge appears in the bottom-right corner showing the total load time.  
Clicking it opens a panel with detailed timings for:

- Application time  
- Database time and query count  
- Client-side load time  
- Combined total time  

You can close the badge using its **✕ (X)** button if it overlaps with elements on your page.  
This only hides it temporarily — it will reappear when the page is reloaded.

The badge is automatically hidden when printing or for non-HTML responses.

Below is how the badge looks on an HTML page.

Collapsed badge:
![Collapsed badge](https://github.com/mvladn/django-load-time-middleware/blob/main/screenshots/collapsed_badge.png) 

Expanded panel:
![Expanded panel](https://github.com/mvladn/django-load-time-middleware/blob/main/screenshots/expanded_badge.png)
