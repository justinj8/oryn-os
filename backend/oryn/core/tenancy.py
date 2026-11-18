from enum import StrEnum


class Role(StrEnum):
    viewer = "viewer"
    operator = "operator"
    admin = "admin"
    owner = "owner"

    @property
    def rank(self) -> int:
        return _RANK[self]


_RANK = {Role.viewer: 0, Role.operator: 1, Role.admin: 2, Role.owner: 3}


def role_at_least(role: Role, minimum: Role) -> bool:
    return role.rank >= minimum.rank
