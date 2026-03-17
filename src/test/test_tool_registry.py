from tools.base_tool import REGISTERED_TOOLS


def test_tools_registered():

    assert len(REGISTERED_TOOLS) > 0