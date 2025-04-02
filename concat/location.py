# TODO: Upgrade hypothesis so I can use type Location = ...
Location = tuple[int, int]


def are_on_same_line_and_offset_by(
    location_x: Location, location_y: Location, characters: int
) -> bool:
    return (
        location_x[0] == location_y[0]
        and location_y[1] - location_x[1] == characters
    )
