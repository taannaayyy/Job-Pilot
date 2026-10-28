def main() -> None:
    import uvicorn

    from jobpilot import config

    uvicorn.run("jobpilot.main:create_app", factory=True, host="127.0.0.1", port=config.api_port())
