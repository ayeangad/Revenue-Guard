"""Worker placeholder: scheduled detection runs (APScheduler later)."""
if __name__ == "__main__":
    from agent.orchestrator.loop import investigate
    from commerce.sim.seed import seed
    seed()
    inc = investigate()
    print(inc.model_dump_json(indent=2)[:2000])
