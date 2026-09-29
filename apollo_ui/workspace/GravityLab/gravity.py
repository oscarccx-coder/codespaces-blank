import math

G = 6.67430e-11  # Gravitational constant



def calculate_gravitational_force(m1, m2, r):
    """Calculate gravitational force between two objects.

    Args:
        m1 (float): Mass of the first object in kilograms.
        m2 (float): Mass of the second object in kilograms.
        r (float): Distance between the centers of the two objects in meters.

    Returns:
        float: Gravitational force in Newtons.
    """
    if m1 <= 0 or m2 <= 0 or r <= 0:
        raise ValueError("Mass and distance must be positive.")
    return G * (m1 * m2) / (r ** 2)



def calculate_escape_velocity(m, r):
    """Calculate escape velocity from a planet.

    Args:
        m (float): Mass of the planet in kilograms.
        r (float): Radius of the planet in meters.

    Returns:
        float: Escape velocity in meters per second.
    """
    if m <= 0 or r <= 0:
        raise ValueError("Mass and radius must be positive.")
    return math.sqrt(2 * G * m / r)



def calculate_orbital_velocity(m, r):
    """Calculate orbital velocity around a planet.

    Args:
        m (float): Mass of the planet in kilograms.
        r (float): Distance from the center of the planet to the orbiting object in meters.

    Returns:
        float: Orbital velocity in meters per second.
    """
    if m <= 0 or r <= 0:
        raise ValueError("Mass and distance must be positive.")
    return math.sqrt(G * m / r)


if __name__ == '__main__':
    try:
        print(calculate_gravitational_force(50, 100, 1))
        print(calculate_escape_velocity(5.972e24, 6.371e6))
        print(calculate_orbital_velocity(5.972e24, 6.371e6 + 40000))
    except ValueError as e:
        print(e)
