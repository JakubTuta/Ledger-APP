import grpc
import pytest
from auth_service.proto import auth_pb2

from .test_base import BaseGrpcTest


@pytest.mark.asyncio
class TestDashboardPanels(BaseGrpcTest):
    async def _register(self, email: str) -> int:
        account = await self.stub.Register(
            auth_pb2.RegisterRequest(email=email, password="password123", plan="pro")
        )
        return account.account_id

    async def _create_panel(self, user_id: int, **fields) -> auth_pb2.Panel:
        request = auth_pb2.CreateDashboardPanelRequest(
            user_id=user_id,
            name=fields.pop("name", "Panel"),
            index=0,
            project_id="1",
            period="last7days",
            **fields,
        )
        return (await self.stub.CreateDashboardPanel(request)).panel

    async def _update_panel(self, user_id: int, panel_id: str, **fields) -> auth_pb2.Panel:
        request = auth_pb2.UpdateDashboardPanelRequest(
            user_id=user_id,
            panel_id=panel_id,
            name="Panel",
            index=0,
            project_id="1",
            period="last7days",
            **fields,
        )
        return (await self.stub.UpdateDashboardPanel(request)).panel

    async def test_metric_panel_can_be_created_before_a_metric_is_chosen(self):
        user_id = await self._register("metric-empty@example.com")

        panel = await self._create_panel(user_id, type="metric_series")

        assert panel.id
        assert not panel.HasField("metric_name")

    async def test_metric_panel_keeps_its_configuration(self):
        user_id = await self._register("metric-config@example.com")

        panel = await self._create_panel(
            user_id,
            type="metric_series",
            metric_name="orders_processed",
            metric_aggregation="sum",
            metric_group_by=["region"],
            metric_tag_filters={"env": "prod"},
            metric_interval="5m",
        )

        assert panel.metric_name == "orders_processed"
        assert panel.metric_aggregation == "sum"
        assert list(panel.metric_group_by) == ["region"]
        assert dict(panel.metric_tag_filters) == {"env": "prod"}
        assert panel.metric_interval == "5m"

    async def test_metric_name_can_be_chosen_after_creation(self):
        user_id = await self._register("metric-late@example.com")
        panel = await self._create_panel(user_id, type="metric_series")

        updated = await self._update_panel(
            user_id, panel.id, type="metric_series", metric_name="queue_depth"
        )

        assert updated.metric_name == "queue_depth"

    async def test_metric_panel_rejects_unknown_aggregation(self):
        user_id = await self._register("metric-bad-agg@example.com")

        with pytest.raises(grpc.aio.AioRpcError) as error:
            await self._create_panel(
                user_id,
                type="metric_series",
                metric_name="orders_processed",
                metric_aggregation="median",
            )

        assert error.value.code() == grpc.StatusCode.INVALID_ARGUMENT

    async def test_error_list_panel_defaults_to_unset_client_error_choice(self):
        user_id = await self._register("errors-default@example.com")

        panel = await self._create_panel(user_id, type="error_list")

        assert not panel.HasField("include_client_errors")

    async def test_error_list_panel_stores_the_client_error_choice(self):
        user_id = await self._register("errors-choice@example.com")

        panel = await self._create_panel(user_id, type="error_list", include_client_errors=False)

        assert panel.HasField("include_client_errors")
        assert panel.include_client_errors is False

        updated = await self._update_panel(
            user_id, panel.id, type="error_list", include_client_errors=True
        )

        assert updated.include_client_errors is True

        listed = (
            await self.stub.GetDashboardPanels(auth_pb2.GetDashboardPanelsRequest(user_id=user_id))
        ).panels
        assert [p.include_client_errors for p in listed] == [True]
