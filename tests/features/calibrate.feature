Feature: Calibrating the judge against the user's buckets
  As the judge's owner
  I want to know if Claude's scores order scenes like my good/meh/bad buckets
  So that I can trust (or reject) the rubric before automating anything

  Scenario: A clean ordering with gates caught passes
    Given a "good" scene "g1" scoring 4.2 with gate passed
    And a "good" scene "g2" scoring 3.8 with gate passed
    And a "meh" scene "m1" scoring 3.0 with gate passed
    And a "bad" scene "b1" scoring 1.5 with gate passed
    And a "bad" scene "b2" scoring 2.0 with gate violated
    And expected gate violators "b2"
    Then calibration passes

  Scenario: A good scene scoring below a bad scene fails
    Given a "good" scene "g1" scoring 1.0 with gate passed
    And a "bad" scene "b1" scoring 2.5 with gate passed
    And no expected gate violators
    Then calibration fails with a cross-bucket inversion

  Scenario: A missed gate violation fails
    Given a "good" scene "g1" scoring 4.0 with gate passed
    And a "bad" scene "b1" scoring 1.0 with gate passed
    And expected gate violators "b1"
    Then calibration fails with an uncaught gate violation

  Scenario: Noise band is the largest score gap across two passes
    Given run A scores g1=4.0 b1=1.0
    And run B scores g1=3.5 b1=1.5
    Then the noise band is 0.5
