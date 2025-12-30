import tasks


def test_task_tax_income_wrapper_handles_exceptions(monkeypatch):
    def raise_exc():
        raise ValueError("boom")

    monkeypatch.setattr(tasks, "tax_income", raise_exc)

    # Should not raise when running the task wrapper
    tasks.task_tax_income.run()


def test_task_generate_province_revenue_wrapper_handles_exceptions(monkeypatch):
    def raise_exc():
        raise RuntimeError("boom")

    monkeypatch.setattr(tasks, "generate_province_revenue", raise_exc)

    tasks.task_generate_province_revenue.run()
