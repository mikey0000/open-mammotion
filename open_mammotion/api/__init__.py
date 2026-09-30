"""One module per specification tag; each exposes one class with one method per endpoint."""

from __future__ import annotations

from open_mammotion.api._base import ApiGroup
from open_mammotion.api.actions import ActionsApi
from open_mammotion.api.devices import DevicesApi
from open_mammotion.api.faults import FaultsApi
from open_mammotion.api.local_network import LocalNetworkApi
from open_mammotion.api.work_reports import WorkReportsApi

__all__ = ["ActionsApi", "ApiGroup", "DevicesApi", "FaultsApi", "LocalNetworkApi", "WorkReportsApi"]
