Feature: The council drives a bot's identity drift
  As the evolution engine
  I want diverse personas' nudges synthesized into identity edits
  So that a bot grows beyond its template across reflections

  Scenario: A reflection adds synthesized facets to a blank identity
    Given a fresh memory db with bot "Geysse" who has said a few things
    When the council reflects with fakes that synthesize "pugs:done with pugs:3" and "music:into metal:2"
    Then bot "Geysse" identity has facet "pugs" with weight 3
    And bot "Geysse" identity has facet "music" with weight 2

  Scenario: Identity accumulates and strengthens across reflections
    Given a fresh memory db with bot "Geysse" who has said a few things
    And bot "Geysse" already has identity facet "pugs" content "wary" weight 2
    When the council reflects with a fake that proposes nudge "pugs:done with pugs:2" and falls back to merge
    Then bot "Geysse" identity has facet "pugs" with weight 4

  Scenario: A reflection prunes weak facets beyond the cap
    Given a fresh memory db with bot "Geysse" who has said a few things
    And bot "Geysse" has 16 weak identity facets at weight 1
    When the council reflects with fakes that synthesize "anchor:a strong new thing:5" and "music:into metal:2"
    Then bot "Geysse" has at most 16 identity facets
    And bot "Geysse" identity has facet "anchor" with weight 5
