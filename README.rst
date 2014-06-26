Reusable app for defining and matching business rules.

To use rule-reactor locally, clone the git repository and run
::
    $ pip install -e /<path-to-rule-reactor>/rule-reactor

You can then import it as
::
    import rules

.. note::
   Because the django-nose test runner only tests packages *within* the
   project directory, rule-reactor has to be tested explicitly
   ::
     $ python manage.py test rules
