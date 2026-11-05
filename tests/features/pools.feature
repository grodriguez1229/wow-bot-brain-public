Feature: Optimizer scene pools
  As the eval substrate
  I want three named, provably-disjoint pools and a way to average a pool
  So that the optimizer never trains and gates on the same scenes

  Scenario: Disjoint pools load and report their sizes
    Given a manifest with golden "g1","g2" eval "e1","e2","e3" heldout "h1","h2"
    When I load the pools
    Then golden has 2, eval has 3, heldout has 2
    And the pools are disjoint

  Scenario: Overlapping pools are rejected
    Given a manifest with golden "g1" eval "e1","g1" heldout "h1"
    When I load the pools
    Then loading raises a disjointness error

  Scenario: Pool mean averages the named scenes' scores
    Given scores e1=2.0 e2=3.0 e3=4.0
    Then the mean of eval "e1","e2","e3" is 3.0
