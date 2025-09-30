from pathlib import Path

import pytest

from bootimage.planner import DiskoExecutor, generate_disko_plan


@pytest.fixture
def sample_plan():
    return {
        "disks": [
            {
                "name": "os",
                "device": "/dev/sda",
                "scheme": "gpt",
                "partitions": [
                    {
                        "name": "ESP",
                        "size": "512MiB",
                        "type": "EF00",
                        "filesystem": {
                            "format": "vfat",
                            "mountpoint": "/boot",
                            "mountOptions": ["umask=0077"],
                        },
                    },
                    {
                        "name": "root",
                        "size": "100%",
                        "filesystem": {
                            "format": "ext4",
                            "mountpoint": "/",
                        },
                    },
                ],
            }
        ],
        "mode": ["destroy", "format", "mount"],
        "disko_flags": ["--yes"],
    }


def test_generate_disko_plan_structure(sample_plan):
    plan = generate_disko_plan(sample_plan)
    disk_config = plan.config["disko.devices"]["disk"]["os"]
    assert disk_config["device"] == "/dev/sda"
    assert disk_config["content"]["type"] == "gpt"
    partitions = disk_config["content"]["partitions"]
    assert set(partitions.keys()) == {"ESP", "root"}
    assert partitions["ESP"]["content"]["format"] == "vfat"
    assert plan.mode == "destroy,format,mount"
    assert plan.flags == ["--yes"]


def test_rendered_nix_contains_expected_sections(sample_plan):
    plan = generate_disko_plan(sample_plan)
    nix_text = plan.render()
    assert "disko.devices" in nix_text
    assert "mountOptions" in nix_text
    assert "\"/boot\"" in nix_text


def test_executor_invokes_runner(tmp_path, sample_plan):
    commands = []
    contents = {}

    def fake_runner(cmd):
        commands.append(cmd)
        path = Path(cmd[-1])
        contents["path"] = path
        contents["text"] = path.read_text()

    executor = DiskoExecutor(runner=fake_runner)
    executor.apply(sample_plan, workdir=tmp_path)

    assert len(commands) == 1
    cmd = commands[0]
    assert cmd[0] == "nix"
    assert "--mode" in cmd
    assert cmd[-1].startswith(str(tmp_path))
    assert "disko.devices" in contents["text"]
    assert not contents["path"].exists()


def test_invalid_plan_missing_disk():
    with pytest.raises(ValueError):
        generate_disko_plan({})


def test_invalid_partition_missing_fs():
    plan = {
        "disks": [
            {
                "device": "/dev/sda",
                "partitions": [
                    {
                        "name": "root",
                        "size": "100%",
                    }
                ],
            }
        ]
    }
    with pytest.raises(ValueError):
        generate_disko_plan(plan)


def test_serialises_boolean_and_numbers():
    plan = {
        "disks": [
            {
                "device": "/dev/sdb",
                "partitions": [
                    {
                        "name": "data",
                        "size": "10G",
                        "filesystem": {
                            "format": "btrfs",
                            "mountpoint": "/data",
                            "mountOptions": ["compress=zstd", True],
                            "extra": {"quota": False, "level": 2},
                        },
                    }
                ],
            }
        ]
    }

    plan_obj = generate_disko_plan(plan)
    rendered = plan_obj.render()
    assert "true" in rendered
    assert "false" in rendered
    assert "level = 2;" in rendered
