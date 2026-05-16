adm_app/
├── app.py                          # Main FastAPI app (modified)
├── requirements.txt                # Updated with anthropic, jinja2, etc.
├── setup.sh                        # Existing setup script
├── adm_app.db                      # SQLite DB (auto-created)
├── downloads/                      # Downloaded files folder
│
├── prompts/                        # NEW DIRECTORY - Step 1-3
│   ├── claude_search_system.txt
│   ├── claude_search_examples.txt
│   └── claude_search_user.jinja2
│
├── config/                         # NEW DIRECTORY - Step 6 & 7
│   ├── __init__.py                 # Makes config a Python package
│   ├── settings.py                 # Main config (ClaudeConfig class)
│   └── .env                        # Environment variables (API keys)
│
├── core/                           # NEW DIRECTORY - Step 4 & 7
│   ├── __init__.py
│   ├── claude_router.py            # ClaudeSearchRouter class
│   └── fallback.py                 # Fallback routing logic
│
├── monitoring/                     # NEW DIRECTORY - Step 9
│   ├── __init__.py
│   ├── claude_monitor.py           # Logging and monitoring
│   └── logs/                       # Log files directory (auto-created)
│       └── claude_routing.log
│
├── tests/                          # NEW DIRECTORY - Step 5
│   ├── __init__.py
│   ├── test_claude_search.py       # Test suite
│   └── test_fallback.py            # Fallback tests
│
├── utils/                          # NEW DIRECTORY - Step 7 (optimizations)
│   ├── __init__.py
│   ├── cache.py                    # Response caching
│   ├── timeout.py                  # Request timeout handling
│   └── cost_tracker.py             # Cost management
│
└── static/                         # Existing frontend
    └── index.html
