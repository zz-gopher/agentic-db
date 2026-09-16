from services.pipeline import SqlPipelineService

if __name__ == "__main__":
    pipeline = SqlPipelineService()
    bad_query = "SELECT * FROM user_logs WHERE DATE(created_at) = '2026-03-01'"

    try:
        final_draft = pipeline.optimize_with_reflection(bad_query)
        print("\n🎉 最终方案:")
        print(final_draft.model_dump_json(indent=2))
    except Exception as e:
        print(f"\n异常终止: {e}")