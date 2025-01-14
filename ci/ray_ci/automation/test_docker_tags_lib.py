from unittest import mock
import sys
from datetime import datetime, timezone
import pytest

from ci.ray_ci.automation.docker_tags_lib import (
    _get_docker_auth_token,
    _get_docker_hub_auth_token,
    _get_image_creation_time,
    delete_tag,
    _list_recent_commit_short_shas,
    query_tags_from_docker_hub,
    query_tags_from_docker_with_oci,
    AuthTokenException,
    RetrieveImageConfigException,
    DockerHubRateLimitException,
)


@mock.patch("requests.get")
def test_get_docker_auth_token(mock_requests):
    namespace = "test_namespace"
    repository = "test_repository"
    mock_requests.return_value = mock.Mock(
        status_code=200, json=mock.MagicMock(return_value={"token": "test_token"})
    )

    token = _get_docker_auth_token(namespace, repository)

    assert mock_requests.call_count == 1
    assert (
        mock_requests.call_args[0][0]
        == f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{namespace}/{repository}:pull"  # noqa
    )
    assert token == "test_token"


@mock.patch("requests.get")
def test_get_docker_auth_token_no_token(mock_requests):
    namespace = "test_namespace"
    repository = "test_repository"
    mock_requests.return_value = mock.Mock(
        status_code=200, json=mock.MagicMock(return_value={})
    )

    token = _get_docker_auth_token(namespace, repository)

    assert mock_requests.call_count == 1
    assert (
        mock_requests.call_args[0][0]
        == f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{namespace}/{repository}:pull"  # noqa
    )
    assert token is None


@mock.patch("requests.get")
def test_get_docker_auth_token_failure(mock_requests):
    namespace = "test_namespace"
    repository = "test_repository"
    mock_requests.return_value = mock.Mock(
        status_code=400, json=mock.MagicMock(return_value={"error": "test_error"})
    )

    with pytest.raises(AuthTokenException, match="Docker. Error code: 400"):
        _get_docker_auth_token(namespace, repository)


@mock.patch("requests.post")
def test_get_docker_hub_auth_token(mock_requests):
    mock_requests.return_value = mock.Mock(
        status_code=200, json=mock.MagicMock(return_value={"token": "test_token"})
    )

    token = _get_docker_hub_auth_token(
        username="test_username", password="test_password"
    )

    assert mock_requests.call_count == 1
    assert mock_requests.call_args[0][0] == "https://hub.docker.com/v2/users/login"
    assert mock_requests.call_args[1]["headers"] == {"Content-Type": "application/json"}
    assert mock_requests.call_args[1]["json"] == {
        "username": "test_username",
        "password": "test_password",
    }
    assert token == "test_token"


@mock.patch("requests.post")
def test_get_docker_hub_auth_token_failure(mock_requests):
    mock_requests.return_value = mock.Mock(
        status_code=400, json=mock.MagicMock(return_value={"error": "test_error"})
    )

    with pytest.raises(AuthTokenException, match="Docker Hub. Error code: 400"):
        _get_docker_hub_auth_token(username="test_username", password="test_password")


@mock.patch("ci.ray_ci.automation.docker_tags_lib._get_git_log")
def test_list_recent_commit_short_shas(mock_git_log):
    mock_git_log.return_value = "a1b2c3\nq2w3e4\nt5y678"

    shas = _list_recent_commit_short_shas()

    assert mock_git_log.call_count == 1
    assert shas == ["a1b2c3", "q2w3e4", "t5y678"]


@mock.patch("ci.ray_ci.automation.docker_tags_lib._get_git_log")
def test_list_recent_commit_short_shas_empty(mock_git_log):
    mock_git_log.return_value = ""

    shas = _list_recent_commit_short_shas(n_days=30)

    mock_git_log.assert_called_once_with(n_days=30)
    assert shas == []


@mock.patch("ci.ray_ci.automation.docker_tags_lib._get_config_docker_oci")
def test_get_image_creation_time(mock_config_docker_oci):
    mock_config_docker_oci.return_value = {
        "architecture": "amd64",
        "created": "2024-01-26T23:00:00.000000000Z",
        "variant": "v1",
    }
    created_time = _get_image_creation_time(tag="test_namespace/test_repo:test_tag")

    mock_config_docker_oci.assert_called_once_with(
        tag="test_tag", namespace="test_namespace", repository="test_repo"
    )
    assert created_time == datetime(2024, 1, 26, 23, 0, tzinfo=timezone.utc)


@mock.patch("ci.ray_ci.automation.docker_tags_lib._get_config_docker_oci")
def test_get_image_creation_time_failure_unknown(mock_config_docker_oci):
    mock_config_docker_oci.side_effect = RetrieveImageConfigException(
        "Failed to retrieve image config."
    )

    with pytest.raises(RetrieveImageConfigException):
        _get_image_creation_time(tag="test_namespace/test_repo:test_tag")
    mock_config_docker_oci.assert_called_once_with(
        tag="test_tag", namespace="test_namespace", repository="test_repo"
    )


@mock.patch("ci.ray_ci.automation.docker_tags_lib._get_config_docker_oci")
def test_get_image_creation_time_failure_no_create_time(mock_config_docker_oci):
    mock_config_docker_oci.return_value = {"architecture": "amd64", "variant": "v1"}
    with pytest.raises(RetrieveImageConfigException):
        _get_image_creation_time(tag="test_namespace/test_repo:test_tag")
    mock_config_docker_oci.assert_called_once_with(
        tag="test_tag", namespace="test_namespace", repository="test_repo"
    )


@mock.patch("requests.delete")
def test_delete_tag(mock_requests):
    namespace = "test_namespace"
    repository = "test_repository"
    tag = "test_tag"
    mock_requests.return_value = mock.Mock(status_code=204)

    deleted = delete_tag(
        tag=f"{namespace}/{repository}:{tag}", docker_hub_token="test_token"
    )
    mock_requests.assert_called_once()
    assert (
        mock_requests.call_args[0][0]
        == f"https://hub.docker.com/v2/repositories/{namespace}/{repository}/tags/{tag}"
    )
    assert mock_requests.call_args[1]["headers"] == {
        "Authorization": "Bearer test_token"
    }
    assert deleted is True


@mock.patch("requests.delete")
def test_delete_tag_failure(mock_requests):
    namespace = "test_namespace"
    repository = "test_repository"
    tag = "test_tag"
    mock_requests.return_value = mock.Mock(status_code=400)

    deleted = delete_tag(
        tag=f"{namespace}/{repository}:{tag}", docker_hub_token="test_token"
    )
    mock_requests.assert_called_once()
    assert (
        mock_requests.call_args[0][0]
        == f"https://hub.docker.com/v2/repositories/{namespace}/{repository}/tags/{tag}"
    )
    assert mock_requests.call_args[1]["headers"] == {
        "Authorization": "Bearer test_token"
    }
    assert deleted is False


@mock.patch("requests.delete")
def test_delete_tag_failure_rate_limit_exceeded(mock_requests):
    namespace = "test_namespace"
    repository = "test_repository"
    tag = "test_tag"
    mock_requests.return_value = mock.Mock(status_code=429)

    with pytest.raises(DockerHubRateLimitException):
        delete_tag(tag=f"{namespace}/{repository}:{tag}", docker_hub_token="test_token")
    mock_requests.assert_called_once()
    assert (
        mock_requests.call_args[0][0]
        == f"https://hub.docker.com/v2/repositories/{namespace}/{repository}/tags/{tag}"
    )
    assert mock_requests.call_args[1]["headers"] == {
        "Authorization": "Bearer test_token"
    }


def _make_docker_hub_response(
    tag: str, page_count: int, namespace: str, repository: str, page_limit: int
):
    next_url = f"https://hub.docker.com/v2/namespaces/{namespace}/repositories/{repository}/tags?page={page_count+1}&page_size=1"  # noqa
    return mock.Mock(
        status_code=200,
        json=mock.MagicMock(
            return_value={
                "count": page_limit,
                "next": next_url if page_count < page_limit else None,
                "previous": "previous_url",
                "results": [{"name": tag}],
            }
        ),
    )


# TODO: use actual filter functions for real use case once they are merged
@pytest.mark.parametrize(
    ("filter_func", "tags", "expected_tags"),
    [
        (
            lambda t: t.startswith("a1s2d3"),
            ["a1s2d3-py38", "2.7.0.q2w3e4", "t5y678-py39-cu123"],
            ["a1s2d3-py38"],
        ),
        (
            lambda t: t.startswith("2.7.0"),
            ["a1s2d3-py38", "2.7.0.q2w3e4", "t5y678-py39-cu123"],
            ["2.7.0.q2w3e4"],
        ),
    ],
)
@mock.patch("requests.get")
def test_query_tags_from_docker_hub(mock_requests, filter_func, tags, expected_tags):
    mock_requests.side_effect = [
        _make_docker_hub_response(
            tags[i], i + 1, "test_namespace", "test_repo", len(tags)
        )
        for i in range(len(tags))
    ]
    queried_tags = query_tags_from_docker_hub(
        filter_func=filter_func,
        namespace="test_namespace",
        repository="test_repo",
        docker_hub_token="test_token",
    )
    expected_tags = sorted([f"test_namespace/test_repo:{t}" for t in expected_tags])

    assert mock_requests.call_count == len(tags)
    assert queried_tags == expected_tags


# TODO: use actual filter functions for real use case once they are merged
@pytest.mark.parametrize(
    ("filter_func", "tags", "expected_tags"),
    [
        (
            lambda t: t.startswith("a1s2d3"),
            ["a1s2d3-py38", "2.7.0.q2w3e4", "t5y678-py39-cu123"],
            ["a1s2d3-py38"],
        ),
    ],
)
@mock.patch("requests.get")
def test_query_tags_from_docker_hub_failure(
    mock_requests, filter_func, tags, expected_tags
):
    mock_requests.side_effect = [
        _make_docker_hub_response(tags[0], 1, "test_namespace", "test_repo", len(tags)),
        mock.Mock(
            status_code=403,
            json=mock.MagicMock(
                return_value={"detail": "Forbidden", "message": "Forbidden"}
            ),
        ),
    ]
    queried_tags = query_tags_from_docker_hub(
        filter_func=filter_func,
        namespace="test_namespace",
        repository="test_repo",
        docker_hub_token="test_token",
    )
    expected_tags = sorted([f"test_namespace/test_repo:{t}" for t in expected_tags[:1]])

    assert mock_requests.call_count == 2
    assert queried_tags == expected_tags


@mock.patch("ci.ray_ci.automation.docker_tags_lib._get_docker_auth_token")
@mock.patch("requests.get")
def test_query_tags_from_docker_with_oci(mock_requests, mock_get_token):
    mock_get_token.return_value = "test_token"
    mock_requests.return_value = mock.Mock(
        status_code=200,
        json=mock.MagicMock(
            return_value={
                "tags": ["test_tag1", "test_tag2", "test_tag3"],
            }
        ),
    )

    tags = query_tags_from_docker_with_oci("test_namespace", "test_repo")
    assert tags == [
        "test_namespace/test_repo:test_tag1",
        "test_namespace/test_repo:test_tag2",
        "test_namespace/test_repo:test_tag3",
    ]


@mock.patch("ci.ray_ci.automation.docker_tags_lib._get_docker_auth_token")
@mock.patch("requests.get")
def test_query_tags_from_docker_with_oci_failure(mock_requests, mock_get_token):
    mock_get_token.return_value = "test_token"
    mock_requests.return_value = mock.Mock(
        status_code=401,
        json=mock.MagicMock(
            return_value={
                "Error": "Unauthorized",
            }
        ),
    )

    with pytest.raises(Exception, match="Failed to query tags"):
        query_tags_from_docker_with_oci("test_namespace", "test_repo")


if __name__ == "__main__":
    sys.exit(pytest.main(["-v", __file__]))
