"""Test for pulse_backoff."""

from time import time

import pytest

from pyadtpulse.pulse_backoff import PulseBackoff


# Test that the PulseBackoff class can be initialized with valid parameters.
def test_initialize_backoff_valid_parameters():
    """
    Test that the PulseBackoff class can be initialized with valid parameters.
    """
    # Arrange
    name = "test_backoff"
    initial_backoff_interval = 1.0
    max_backoff_interval = 10.0
    threshold = 0
    debug_locks = False
    detailed_debug_logging = False

    # Store the current time
    current_time = time()

    # Act
    backoff = PulseBackoff(
        name,
        initial_backoff_interval,
        max_backoff_interval,
        threshold,
        debug_locks,
        detailed_debug_logging,
    )

    # Assert
    assert backoff.name == name
    assert backoff.initial_backoff_interval == initial_backoff_interval
    assert backoff._max_backoff_interval == max_backoff_interval
    assert backoff._backoff_count == 0
    assert backoff._expiration_time == 0.0


# Get current backoff interval
def test_get_current_backoff_interval():
    """
    Test that the get_current_backoff_interval method returns the correct current backoff interval.
    """
    # Arrange
    name = "test_backoff"
    initial_backoff_interval = 1.0
    max_backoff_interval = 10.0
    threshold = 0
    debug_locks = False
    detailed_debug_logging = False
    backoff = PulseBackoff(
        name,
        initial_backoff_interval,
        max_backoff_interval,
        threshold,
        debug_locks,
        detailed_debug_logging,
    )

    # Act
    current_backoff_interval = backoff.get_current_backoff_interval()
    assert current_backoff_interval == 0.0
    backoff.increment_backoff()
    current_backoff_interval = backoff.get_current_backoff_interval()
    # Assert
    assert current_backoff_interval == initial_backoff_interval
    backoff.increment_backoff()
    current_backoff_interval = backoff.get_current_backoff_interval()
    assert current_backoff_interval == initial_backoff_interval * 2


# Increment backoff
def test_increment_backoff():
    """
    Test that the increment_backoff method increments the backoff count.
    """
    # Arrange
    name = "test_backoff"
    initial_backoff_interval = 1.0
    max_backoff_interval = 10.0
    threshold = 0
    debug_locks = False
    detailed_debug_logging = False
    backoff = PulseBackoff(
        name,
        initial_backoff_interval,
        max_backoff_interval,
        threshold,
        debug_locks,
        detailed_debug_logging,
    )

    # Act
    backoff.increment_backoff()

    # Assert
    assert backoff._backoff_count == 1
    backoff.increment_backoff()
    assert backoff._backoff_count == 2


# Reset backoff
def test_reset_backoff():
    """
    Test that the reset_backoff method resets the backoff count and expiration time.
    """
    # Arrange
    name = "test_backoff"
    initial_backoff_interval = 1.0
    max_backoff_interval = 10.0
    threshold = 0
    debug_locks = False
    detailed_debug_logging = False
    backoff = PulseBackoff(
        name,
        initial_backoff_interval,
        max_backoff_interval,
        threshold,
        debug_locks,
        detailed_debug_logging,
    )
    backoff.increment_backoff()

    # Act
    backoff.reset_backoff()

    # Assert
    assert backoff._backoff_count == 0


# Test that the wait_for_backoff method waits for the correct amount of time.
@pytest.mark.asyncio
async def test_wait_for_backoff2(mock_sleep):
    """
    Test that the wait_for_backoff method waits for the correct amount of time.
    """
    # Arrange

    name = "test_backoff"
    initial_backoff_interval = 1.0
    max_backoff_interval = 10.0
    threshold = 0
    debug_locks = False
    detailed_debug_logging = False
    backoff = PulseBackoff(
        name,
        initial_backoff_interval,
        max_backoff_interval,
        threshold,
        debug_locks,
        detailed_debug_logging,
    )

    # Act
    await backoff.wait_for_backoff()
    assert mock_sleep.call_count == 0
    backoff.increment_backoff()
    await backoff.wait_for_backoff()
    assert mock_sleep.await_args[0][0] == pytest.approx(initial_backoff_interval)


# Check if backoff is needed
def test_will_backoff():
    """
    Test that the will_backoff method returns True if backoff is needed, False otherwise.
    """
    # Arrange
    name = "test_backoff"
    initial_backoff_interval = 1.0
    max_backoff_interval = 10.0
    threshold = 0
    debug_locks = False
    detailed_debug_logging = False
    backoff = PulseBackoff(
        name,
        initial_backoff_interval,
        max_backoff_interval,
        threshold,
        debug_locks,
        detailed_debug_logging,
    )

    # Act and Assert
    assert not backoff.will_backoff()

    backoff.increment_backoff()
    assert backoff.will_backoff()


# Initialize backoff with invalid initial_backoff_interval
def test_initialize_backoff_invalid_initial_interval():
    """
    Test that initializing the PulseBackoff class with an invalid
    initial_backoff_interval raises a ValueError.
    """
    # Arrange
    name = "test_backoff"
    initial_backoff_interval = -1.0
    max_backoff_interval = 10.0
    threshold = 0
    debug_locks = False
    detailed_debug_logging = False

    # Act and Assert
    with pytest.raises(ValueError):
        PulseBackoff(
            name,
            initial_backoff_interval,
            max_backoff_interval,
            threshold,
            debug_locks,
            detailed_debug_logging,
        )


# Initialize backoff with invalid max_backoff_interval
def test_initialize_backoff_invalid_max_interval():
    """
    Test that initializing the PulseBackoff class with an invalid
    max_backoff_interval raises a ValueError.
    """
    # Arrange
    name = "test_backoff"
    initial_backoff_interval = 1.0
    max_backoff_interval = 0.5
    threshold = 0
    debug_locks = False
    detailed_debug_logging = False

    # Act and Assert
    with pytest.raises(ValueError):
        PulseBackoff(
            name,
            initial_backoff_interval,
            max_backoff_interval,
            threshold,
            debug_locks,
            detailed_debug_logging,
        )


# Test that setting the absolute backoff time with an invalid backoff_time raises a ValueError.
def test_set_absolute_backoff_time_invalid_time():
    """
    Test that setting the absolute backoff time with an invalid backoff_time raises a ValueError.
    """
    # Arrange
    backoff = PulseBackoff(
        name="test_backoff",
        initial_backoff_interval=1.0,
        max_backoff_interval=10.0,
        threshold=0,
        debug_locks=False,
        detailed_debug_logging=False,
    )

    # Act and Assert
    with pytest.raises(
        ValueError, match="Absolute backoff time must be greater than current time"
    ):
        backoff.set_absolute_backoff_time(time() - 1)


def test_set_absolute_backoff_time_valid_time():
    """
    Test that setting the absolute backoff time with a valid backoff_time works.
    """
    # Arrange
    backoff = PulseBackoff(
        name="test_backoff",
        initial_backoff_interval=1.0,
        max_backoff_interval=10.0,
        threshold=0,
        debug_locks=False,
        detailed_debug_logging=False,
    )

    # Act and Assert
    backoff_time = time() + 10
    backoff.set_absolute_backoff_time(backoff_time)
    assert backoff._expiration_time == backoff_time


# Initialize backoff with valid parameters
def test_initialize_backoff_valid_parameters2():
    """
    Test that the PulseBackoff class can be initialized with valid parameters.
    """
    # Arrange
    name = "test_backoff"
    initial_backoff_interval = 1.0
    max_backoff_interval = 10.0
    threshold = 0
    debug_locks = False
    detailed_debug_logging = False

    # Act
    backoff = PulseBackoff(
        name,
        initial_backoff_interval,
        max_backoff_interval,
        threshold,
        debug_locks,
        detailed_debug_logging,
    )

    # Assert
    assert backoff.name == name
    assert backoff.initial_backoff_interval == initial_backoff_interval
    assert backoff._max_backoff_interval == max_backoff_interval
    assert backoff._backoff_count == 0
    assert backoff._expiration_time == 0.0


# Increment backoff
def test_increment_backoff2():
    """
    Test that the backoff count is incremented correctly when calling the
    increment_backoff method.
    """
    # Arrange
    name = "test_backoff"
    initial_backoff_interval = 1.0
    max_backoff_interval = 10.0
    threshold = 0
    debug_locks = False
    detailed_debug_logging = False
    backoff = PulseBackoff(
        name,
        initial_backoff_interval,
        max_backoff_interval,
        threshold,
        debug_locks,
        detailed_debug_logging,
    )

    # Act
    backoff.increment_backoff()

    # Assert
    assert backoff.backoff_count == 1


# Reset backoff
def test_reset_backoff2():
    """
    Test that the backoff count and expiration time are not reset when calling
    the reset_backoff method where expiration time is in the future.
    """
    # Arrange
    name = "test_backoff"
    initial_backoff_interval = 1.0
    max_backoff_interval = 10.0
    threshold = 0
    debug_locks = False
    detailed_debug_logging = False
    backoff = PulseBackoff(
        name,
        initial_backoff_interval,
        max_backoff_interval,
        threshold,
        debug_locks,
        detailed_debug_logging,
    )
    now = time()
    backoff._backoff_count = 5
    backoff._expiration_time = now + 10.0

    # Act
    backoff.reset_backoff()

    # Assert
    assert backoff._backoff_count == 5
    assert backoff._expiration_time == now + 10.0
    assert backoff.expiration_time == now + 10.0


# Check if backoff is needed
def test_backoff_needed():
    """
    Test that the 'will_backoff' method returns the correct value when
    backoff is needed.
    """
    # Arrange
    name = "test_backoff"
    initial_backoff_interval = 1.0
    max_backoff_interval = 10.0
    threshold = 0
    debug_locks = False
    detailed_debug_logging = False

    backoff = PulseBackoff(
        name,
        initial_backoff_interval,
        max_backoff_interval,
        threshold,
        debug_locks,
        detailed_debug_logging,
    )

    # Act
    backoff.increment_backoff()

    # Assert
    assert backoff.will_backoff() is True


# Wait for backoff
@pytest.mark.asyncio
async def test_wait_for_backoff(mocker):
    """
    Test that the wait_for_backoff method waits for the correct amount of time.
    """
    # Arrange
    name = "test_backoff"
    initial_backoff_interval = 1.0
    max_backoff_interval = 10.0
    threshold = 0
    debug_locks = False
    detailed_debug_logging = False
    name = "test_backoff"
    initial_backoff_interval = 1.0
    max_backoff_interval = 10.0
    threshold = 0
    debug_locks = False
    detailed_debug_logging = False

    backoff = PulseBackoff(
        name,
        initial_backoff_interval,
        max_backoff_interval,
        threshold,
        debug_locks,
        detailed_debug_logging,
    )
    # Act
    await backoff.wait_for_backoff()
    assert backoff.expiration_time == 0.0
    backoff.increment_backoff()
    # Assert
    assert backoff.expiration_time == 0.0


# Set initial backoff interval
def test_set_initial_backoff_interval():
    """
    Test that the initial backoff interval can be set.
    """
    # Arrange
    name = "test_backoff"
    initial_backoff_interval = 1.0
    max_backoff_interval = 10.0
    threshold = 0
    debug_locks = False
    detailed_debug_logging = False
    backoff = PulseBackoff(
        name,
        initial_backoff_interval,
        max_backoff_interval,
        threshold,
        debug_locks,
        detailed_debug_logging,
    )

    # Act
    new_interval = 2.0
    backoff.initial_backoff_interval = new_interval

    # Assert
    assert backoff.initial_backoff_interval == new_interval


# Initialize backoff with invalid max_backoff_interval
def test_initialize_backoff_invalid_max_interval2():
    """
    Test that the PulseBackoff class raises a ValueError when initialized
    with an invalid max_backoff_interval.
    """
    # Arrange
    name = "test_backoff"
    initial_backoff_interval = 1.0
    max_backoff_interval = 0.5
    threshold = 0
    debug_locks = False
    detailed_debug_logging = False

    # Act & Assert
    with pytest.raises(ValueError):
        PulseBackoff(
            name,
            initial_backoff_interval,
            max_backoff_interval,
            threshold,
            debug_locks,
            detailed_debug_logging,
        )


def test_initialize_backoff_invalid_initial_interval2():
    """
    Test that the PulseBackoff class raises a ValueError when initialized with an
    invalid initial_backoff_interval.
    """
    # Arrange
    name = "test_backoff"
    initial_backoff_interval = -1.0
    max_backoff_interval = 10.0
    threshold = 0
    debug_locks = False
    detailed_debug_logging = False

    # Act & Assert
    with pytest.raises(ValueError):
        PulseBackoff(
            name,
            initial_backoff_interval,
            max_backoff_interval,
            threshold,
            debug_locks,
            detailed_debug_logging,
        )


# Set absolute backoff time with invalid backoff_time
def test_set_absolute_backoff_time_invalid_backoff_time():
    """
    Test that set_absolute_backoff_time raises a ValueError when given an invalid backoff_time.
    """
    # Arrange
    name = "test_backoff"
    initial_backoff_interval = 1.0
    max_backoff_interval = 10.0
    threshold = 0
    debug_locks = False
    detailed_debug_logging = False
    backoff = PulseBackoff(
        name,
        initial_backoff_interval,
        max_backoff_interval,
        threshold,
        debug_locks,
        detailed_debug_logging,
    )

    # Act and Assert
    invalid_backoff_time = time() - 1
    with pytest.raises(ValueError):
        backoff.set_absolute_backoff_time(invalid_backoff_time)


# Wait for backoff with negative diff
@pytest.mark.asyncio
async def test_wait_for_backoff_with_negative_diff(mocker):
    """
    Test that the wait_for_backoff method handles a negative diff correctly.
    """
    # Arrange
    name = "test_backoff"
    initial_backoff_interval = 1.0
    max_backoff_interval = 10.0
    threshold = 0
    debug_locks = False
    detailed_debug_logging = False

    backoff = PulseBackoff(
        name,
        initial_backoff_interval,
        max_backoff_interval,
        threshold,
        debug_locks,
        detailed_debug_logging,
    )

    # Set the expiration time to a past time
    backoff._expiration_time = time() - 1

    start_time = time()

    # Act
    await backoff.wait_for_backoff()

    # Assert
    assert backoff._expiration_time >= initial_backoff_interval


# Calculate backoff interval with backoff_count <= threshold
def test_calculate_backoff_interval_with_backoff_count_less_than_threshold():
    """
    Test that the calculate_backoff_interval method returns 0
    when the backoff count is less than or equal to the threshold.
    """
    # Arrange
    name = "test_backoff"
    initial_backoff_interval = 1.0
    max_backoff_interval = 10.0
    threshold = 5
    debug_locks = False
    detailed_debug_logging = False

    backoff = PulseBackoff(
        name,
        initial_backoff_interval,
        max_backoff_interval,
        threshold,
        debug_locks,
        detailed_debug_logging,
    )

    # Act
    result = backoff._calculate_backoff_interval()

    # Assert
    assert result == 0.0


# Calculate backoff interval with backoff_count > threshold and exceeds max_backoff_interval
@pytest.mark.asyncio
async def test_calculate_backoff_interval_exceeds_max(mocker):
    """
    Test that the calculate_backoff_interval method returns the correct backoff interval
    when backoff_count is greater than threshold and exceeds max_backoff_interval.
    """
    # Arrange
    name = "test_backoff"
    initial_backoff_interval = 1.0
    max_backoff_interval = 10.0
    threshold = 0
    debug_locks = False
    detailed_debug_logging = False

    backoff = PulseBackoff(
        name,
        initial_backoff_interval,
        max_backoff_interval,
        threshold,
        debug_locks,
        detailed_debug_logging,
    )

    backoff._backoff_count = 2

    # Act
    result = backoff._calculate_backoff_interval()

    # Assert
    assert result == 2.0
    backoff._backoff_count = 3
    result = backoff._calculate_backoff_interval()
    assert result == 4.0
    backoff._backoff_count = 4
    result = backoff._calculate_backoff_interval()
    assert result == 8.0
    backoff._backoff_count = 5
    result = backoff._calculate_backoff_interval()
    assert result == max_backoff_interval
    backoff._backoff_count = 6
    result = backoff._calculate_backoff_interval()
    assert result == max_backoff_interval

    name = "test_backoff"
    initial_backoff_interval = 1.0
    max_backoff_interval = 10.0
    threshold = 3
    debug_locks = False
    detailed_debug_logging = False

    backoff = PulseBackoff(
        name,
        initial_backoff_interval,
        max_backoff_interval,
        threshold,
        debug_locks,
        detailed_debug_logging,
    )

    backoff._backoff_count = 2

    # Act
    result = backoff._calculate_backoff_interval()

    # Assert
    assert result == 1.0
    backoff._backoff_count = 3
    result = backoff._calculate_backoff_interval()
    assert result == 1.0
    backoff._backoff_count = 4
    result = backoff._calculate_backoff_interval()
    assert result == initial_backoff_interval
    backoff._backoff_count = 5
    result = backoff._calculate_backoff_interval()
    assert result == initial_backoff_interval * 2
    backoff._backoff_count = 6
    result = backoff._calculate_backoff_interval()
    assert result == initial_backoff_interval * 4
    backoff._backoff_count = 7
    result = backoff._calculate_backoff_interval()
    assert result == initial_backoff_interval * 8
    backoff._backoff_count = 8
    result = backoff._calculate_backoff_interval()
    assert result == max_backoff_interval
    backoff._backoff_count = 9
    result = backoff._calculate_backoff_interval()
    assert result == max_backoff_interval


# Increment backoff and update expiration_time
def test_increment_backoff_and_update_expiration_time():
    """
    Test that the backoff count is incremented
    """
    # Arrange
    name = "test_backoff"
    initial_backoff_interval = 1.0
    max_backoff_interval = 10.0
    threshold = 0
    debug_locks = False
    detailed_debug_logging = False
    backoff = PulseBackoff(
        name,
        initial_backoff_interval,
        max_backoff_interval,
        threshold,
        debug_locks,
        detailed_debug_logging,
    )
    name = "test_backoff"
    initial_backoff_interval = 1.0
    max_backoff_interval = 10.0
    threshold = 0
    debug_locks = False
    detailed_debug_logging = False
    backoff = PulseBackoff(
        name,
        initial_backoff_interval,
        max_backoff_interval,
        threshold,
        debug_locks,
        detailed_debug_logging,
    )
    # Act
    backoff.increment_backoff()

    # Assert
    assert backoff.backoff_count == 1


# Calculate backoff interval with backoff_count > threshold
def test_calculate_backoff_interval_with_backoff_count_greater_than_threshold():
    """
    Test the calculation of backoff interval when backoff_count is greater than threshold.
    """
    # Arrange
    name = "test_backoff"
    initial_backoff_interval = 1.0
    max_backoff_interval = 10.0
    threshold = 0
    debug_locks = False
    detailed_debug_logging = False
    backoff_count = 5

    backoff = PulseBackoff(
        name,
        initial_backoff_interval,
        max_backoff_interval,
        threshold,
        debug_locks,
        detailed_debug_logging,
    )
    backoff._backoff_count = backoff_count

    # Act
    calculated_interval = backoff._calculate_backoff_interval()

    # Assert
    expected_interval = initial_backoff_interval * (2 ** (backoff_count - threshold))
    assert calculated_interval == min(expected_interval, max_backoff_interval)


# Test that calling increment backoff 4 times followed by wait for backoff
# will sleep for 8 seconds with an initial backoff of 1, max backoff of 10.
# And that an additional call to increment backoff followed by a wait for backoff will wait for 10.


@pytest.mark.asyncio
async def test_increment_backoff_and_wait_for_backoff(mock_sleep):
    """
    Test that calling increment backoff 4 times followed by wait for backoff will
    sleep for 8 seconds with an initial backoff of 1, max backoff of 10.
    And that an additional call to increment backoff followed by a wait
    for backoff will wait for 10.
    """
    # Arrange
    name = "test_backoff"
    initial_backoff_interval = 1.0
    max_backoff_interval = 10.0
    threshold = 0
    debug_locks = False
    detailed_debug_logging = False

    # Create a PulseBackoff object
    backoff = PulseBackoff(
        name,
        initial_backoff_interval,
        max_backoff_interval,
        threshold,
        debug_locks,
        detailed_debug_logging,
    )

    # Act
    await backoff.wait_for_backoff()
    assert mock_sleep.call_count == 0
    backoff.increment_backoff()

    await backoff.wait_for_backoff()
    assert mock_sleep.call_count == 1
    assert mock_sleep.call_args_list[0][0][0] == initial_backoff_interval
    backoff.increment_backoff()

    await backoff.wait_for_backoff()
    assert mock_sleep.call_count == 2
    assert mock_sleep.call_args_list[1][0][0] == 2 * initial_backoff_interval
    backoff.increment_backoff()

    await backoff.wait_for_backoff()
    assert mock_sleep.call_count == 3
    assert mock_sleep.call_args_list[2][0][0] == 4 * initial_backoff_interval
    backoff.increment_backoff()

    # Additional call after 4 iterations
    await backoff.wait_for_backoff()
    assert mock_sleep.call_count == 4
    assert mock_sleep.call_args_list[3][0][0] == 8 * initial_backoff_interval
    backoff.increment_backoff()

    await backoff.wait_for_backoff()
    assert mock_sleep.call_count == 5
    assert mock_sleep.call_args_list[4][0][0] == max_backoff_interval
    backoff.increment_backoff()
    await backoff.wait_for_backoff()
    assert mock_sleep.call_count == 6
    assert mock_sleep.call_args_list[4][0][0] == max_backoff_interval


@pytest.mark.asyncio
async def test_absolute_backoff_time(mock_sleep, freeze_time_to_now):
    """
    Test that the absolute backoff time is calculated correctly.
    """
    # Arrange
    name = "test_backoff"
    initial_backoff_interval = 1.0
    max_backoff_interval = 10.0
    threshold = 0
    debug_locks = False
    detailed_debug_logging = False
    backoff = PulseBackoff(
        name,
        initial_backoff_interval,
        max_backoff_interval,
        threshold,
        debug_locks,
        detailed_debug_logging,
    )

    # Act
    backoff.set_absolute_backoff_time(time() + 100)
    assert backoff._backoff_count == 0
    backoff.reset_backoff()
    # make sure backoff can't be reset
    assert backoff.expiration_time == time() + 100
    await backoff.wait_for_backoff()
    assert mock_sleep.call_count == 1
    assert mock_sleep.call_args_list[0][0][0] == 100
