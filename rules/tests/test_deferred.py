from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from rules.deferred import *

dlist = lambda *a: DeferredTuple(a)


class TestDeferred(TestCase):
    def test_init(self):
        self.assertRaises(TypeError, DeferredValue)

    def test_issubclass(self):
        self.assertTrue(issubclass(DeferredDict, Deferred))
        self.assertTrue(issubclass(DeferredTuple, Deferred))
        self.assertTrue(issubclass(DeferredValue, Deferred))
        self.assertTrue(issubclass(Selector, DeferredValue))
        self.assertTrue(issubclass(Function, DeferredValue))

    def test_isinstance(self):
        self.assertTrue(isinstance(DeferredDict(), Deferred))
        self.assertTrue(isinstance(DeferredTuple(), Deferred))
        self.assertTrue(isinstance(Selector(('const', 0), ()), DeferredValue))
        self.assertTrue(isinstance(Function('min', (0, 1)), DeferredValue))


class TestSelector(TestCase):
    def test_init(self):
        self.assertRaises(TypeError, Selector, (1, 2, 3), ())
        self.assertRaises(TypeError, Selector, (1, 2, 3))
        self.assertRaises(NotImplementedError, Selector, 'hello', ())
        # We don't try to coerce numbers or numeric strings.
        self.assertRaises(NotImplementedError, Selector, '1', ())
        self.assertRaises(NotImplementedError, Selector, 1., ())

    def test_init_model(self):
        ct = ContentType.objects.all()[0]
        model = ct.app_label + '.' + ct.model
        s = Selector(('model', model), ())
        self.assertEqual(s.stype, 'model')
        self.assertEqual(s.arg, model)
        self.assertIs(s.first(None), ct.model_class())
        self.assertRaises(TypeError, Selector, ('model', 'random.model.malformatted'), ())
        self.assertRaises(ContentType.DoesNotExist, Selector, ('model', 'random.model'), ())
        self.assertRaises(AttributeError, Selector, 'model', ())

    def test_maybe_const_model(self):
        ct = ContentType.objects.all()[0]
        model = ct.app_label + '.' + ct.model
        s = Selector(('model', model), ())
        self.assertIs(s.maybe_const(), ct.model_class())
        s1 = Selector(('model', model), ('objects',))
        self.assertRaises(StillDeferred, s1.maybe_const)

    def test_init_const(self):
        s = Selector('const', ())
        self.assertEqual(s.stype, 'const')
        self.assertIs(s.arg, None)
        self.assertIs(s.first(None), None)
        s = Selector(('const', 1), ())
        self.assertEqual(s.stype, 'const')
        self.assertEqual(s.arg, 1)
        self.assertEqual(s.first(None), 1)
        self.assertRaises(AssertionError, Selector, 'const', (1,))

    def test_maybe_const_const(self):
        s = Selector('const', ())
        self.assertIs(s.maybe_const(), None)
        s = Selector(('const', 1), ())
        self.assertEqual(s.maybe_const(), 1)

    def test_init_extra(self):
        s = Selector('extra', ())
        self.assertEqual(s.stype, 'extra')
        self.assertRaises(TypeError, s.first, None)
        self.assertRaises(KeyError, s.first, {})
        self.assertEqual(s.first({'extra': 1}), 1)
        self.assertRaises(StillDeferred, s.maybe_const)

    def test_init_int(self):
        s = Selector(0, ())
        self.assertEqual(s.stype, 0)
        self.assertRaises(TypeError, s.first, None)
        self.assertRaises(KeyError, s.first, {})
        self.assertRaises(IndexError, s.first, {'objects': ()})
        self.assertEqual(s.first({'objects': [5]}), 5)
        self.assertRaises(StillDeferred, s.maybe_const)

    def test_init_deferred(self):
        s0 = Selector(0, ())
        s = Selector(s0, ())
        self.assertIs(s.stype, s0)
        self.assertRaises(TypeError, s.first, None)
        self.assertRaises(KeyError, s.first, {})
        self.assertRaises(IndexError, s.first, {'objects': ()})
        self.assertEqual(s.first({'objects': [5]}), 5)
        s1 = Selector('const', ())
        s = Selector(s1, ())
        self.assertIs(s.first({}), None)

    def test_maybe_const_deferred(self):
        s0 = Selector(0, ())
        s = Selector(s0, ())
        self.assertRaises(StillDeferred, s.maybe_const)
        s = Selector(s0, ('x',))
        self.assertRaises(StillDeferred, s.maybe_const)
        s1 = Selector(('const', 5), ())
        s = Selector(s1, ())
        self.assertEqual(s.maybe_const(), 5)
        s = Selector(s1, ('x',))
        self.assertRaises(StillDeferred, s.maybe_const)

    def test_init_chain(self):
        s1 = Selector('const', None)
        s2 = Selector(0, ('x',))
        s = Selector(0, [s1, s2])
        self.assertEqual(s.chain, (s1, s2))
        self.assertTrue(isinstance(s.chain, DeferredTuple))

    def test_eq(self):
        s1 = Selector(1, ['x'])
        s2 = Selector(1, ['x'])
        s3 = Selector(1, ['y'])
        s4 = Selector(2, ['x'])
        self.assertEqual(s1, s1)
        self.assertEqual(s1, s2)
        self.assertNotEqual(s1, s3)
        self.assertNotEqual(s1, s4)
        f = Function('sum', ())
        self.assertNotEqual(s1, f)

    def test_get_value(self):
        s = Selector(('const', 5), None)
        i = {}
        self.assertEqual(s.get_value(i), 5)
        i[id(s)] = 4
        self.assertEqual(s.get_value(i), 5)
        s = Selector(0, None)
        self.assertEqual(s.chain, DeferredTuple())

    def test_get_value_from_dict(self):
        s = Selector('extra', ('one',))
        self.assertEqual(s.get_value({'extra': {'one': 1}}), 1)
        self.assertRaises(ChainError, s.get_value, {'extra': None})
        self.assertRaises(ChainError, s.get_value, {'extra': {}})

    def test_get_value_from_list(self):
        s = Selector('extra', (0,))
        self.assertEqual(s.get_value({'extra': [1]}), 1)
        self.assertRaises(ChainError, s.get_value, {'extra': None})
        self.assertRaises(ChainError, s.get_value, {'extra': []})

    def test_get_value_callable_simple(self):
        s = Selector(0, [['__str__', 42]])
        # Passing a list to represent a call is unexpected
        self.assertRaises(ChainError, s.get_value, {'objects': [int]})
        s = Selector(0, [dlist('__str__', 42)])
        self.assertEqual(s.get_value({'objects': [int]}), '42')
        # Function will raise a TypeError, gets converted to ChainError.
        self.assertRaises(ChainError, s.get_value, {'objects': [str]})

    def test_get_value_callable_args(self):
        s = Selector(('model', 'contenttypes.contenttype'),
                     ('objects', ('values', ['app_label', 'model'])))
        x = s.get_value({})
        self.assertTrue(x)
        self.assertTrue(isinstance(x[0], dict))
        self.assertIn('app_label', x[0])
        self.assertIn('model', x[0])

    def test_get_value_callable_deferred_args(self):
        args = DeferredTuple(['app_label', Selector(0, ())])
        s = Selector(('model', 'contenttypes.contenttype'),
                     ('objects', ('values', args)))
        self.assertRaises(ChainError, s.get_value, {})
        x = s.get_value({'objects': ['model']})
        self.assertTrue(x)
        self.assertTrue(isinstance(x[0], dict))
        self.assertIn('app_label', x[0])
        self.assertIn('model', x[0])
        self.assertNotIn('name', x[0])
        # Changing the input now changes the output
        x = s.get_value({'objects': ['name']})
        self.assertTrue(x)
        self.assertTrue(isinstance(x[0], dict))
        self.assertIn('app_label', x[0])
        self.assertNotIn('model', x[0])
        self.assertIn('name', x[0])

    def test_get_value_callable_kwargs(self):
        s = Selector(('model', 'contenttypes.contenttype'),
                     ('objects', ('filter', {'app_label': 'contenttypes'})))
        x = s.get_value({})
        self.assertEqual(len(x), 1)
        self.assertTrue(isinstance(x[0], ContentType))
        self.assertEqual(x[0].app_label, 'contenttypes')

    def test_get_value_callable_deferred_args(self):
        kwargs = DeferredDict({'app_label': Selector(0, None)})
        s = Selector(('model', 'contenttypes.contenttype'),
                     ('objects', dlist('filter', kwargs)))
        self.assertRaises(ChainError, s.get_value, {})
        x = s.get_value({'objects': ['contenttypes']})
        self.assertEqual(len(x), 1)
        self.assertTrue(isinstance(x[0], ContentType))
        self.assertEqual(x[0].app_label, 'contenttypes')
        x = s.get_value({'objects': ['random']})
        self.assertEqual(len(x), 0)

    def test_str(self):
        s = Selector(('model', 'contenttypes.contenttype'), ('objects', 'all'))
        self.assertEqual(str(s), 'model:contenttypes.contenttype.objects.all')
        s = Selector(('const', 3), None)
        self.assertEqual(str(s), 'const:3')
        s = Selector(s, ('hello',))
        self.assertEqual(str(s), 'const:3.hello')


class TestFunction(TestCase):
    def test_init(self):
        f = Function('sum', [(1, 2, 3)])
        self.assertIs(f.func, sum)
        self.assertEqual(f.name, 'sum')
        self.assertEqual(f.args, ((1, 2, 3),))
        self.assertRaises(KeyError, Function, 'random', ())
        f = Function('sum', DeferredTuple([(1, 2, 3)]))
        # because maybe_const is called
        self.assertEqual(f.args, ((1, 2, 3),))
        self.assertEqual(str(f), 'sum((1, 2, 3))')

    def test_get_value(self):
        i = {}
        f = Function('sum', [(1, 2, 3)])
        x = f.get_value(i)
        self.assertEqual(x, 6)
        i[id(f)] = 8
        self.assertEqual(f.get_value(i), 6)
        f.args = DeferredTuple([(3, 4, 5)])
        self.assertEqual(f.get_value(i), 6)
        self.assertEqual(f._get_value(i), 12)

    def test_maybe_const(self):
        f = Function('sum', [(1, 2, 3)])
        self.assertEqual(f.maybe_const(), 6)
        s = Selector(0, ())
        f = Function('sum', DeferredTuple([DeferredTuple([s, 2, 3])]))
        self.assertRaises(StillDeferred, f.maybe_const)

    def test_get_value_with_selector(self):
        i = {'objects': (1,)}
        s = Selector(0, ())
        f = Function('sum', DeferredTuple([DeferredTuple([s, 2, 3])]))
        self.assertEqual(f.get_value(i), 6)
        i['objects'] = (2,)
        self.assertEqual(f.get_value(i), 6)
        i = {'objects': (2,)}
        self.assertEqual(f.get_value(i), 7)

    def test_eq(self):
        f1 = Function('sum', [(1, 2, 3)])
        f2 = Function('sum', [(1, 2, 3)])
        f3 = Function('set', [(1, 2, 3)])
        f4 = Function('sum', [(1, 3)])
        self.assertEqual(f1, f1)
        self.assertEqual(f1, f2)
        self.assertNotEqual(f1, f3)
        self.assertNotEqual(f1, f4)
        s = Selector(0, ())
        self.assertNotEqual(f1, s)


class TestDeferredDict(TestCase):
    def test_maybe_const(self):
        d = DeferredDict()
        self.assertIsNot(d.maybe_const(), d)
        self.assertEqual(d.maybe_const(), {})
        d = DeferredDict({'one': 1})
        self.assertIsNot(d.maybe_const(), d)
        self.assertEqual(d.maybe_const(), {'one': 1})
        d = DeferredDict({'one': Function('max', (2, 4))})
        self.assertIsNot(d.maybe_const(), d)
        self.assertEqual(d.maybe_const(), {'one': 4})
        d = DeferredDict({'one': Selector(0, None)})
        self.assertRaises(StillDeferred, d.maybe_const)

    def test_get_value(self):
        d = DeferredDict({'one': Selector(0, None), 'two': 2})
        self.assertEqual(d.get_value({'objects': [1]}), {'one': 1, 'two': 2})
        self.assertEqual(d.get_value({'objects': ['one']}), {'one': 'one', 'two': 2})


class TestDeferredTuple(TestCase):
    def test_maybe_const(self):
        l = DeferredTuple()
        self.assertIsNot(l.maybe_const(), l)
        self.assertEqual(l.maybe_const(), ())
        l = DeferredTuple(['one', 1])
        self.assertIsNot(l.maybe_const(), l)
        self.assertEqual(l.maybe_const(), ('one', 1))
        l = DeferredTuple(('one', Function('max', (2, 4))))
        self.assertIsNot(l.maybe_const(), l)
        self.assertEqual(l.maybe_const(), ('one', 4))
        l = DeferredTuple(['one', Selector(0, None)])
        self.assertRaises(StillDeferred, l.maybe_const)

    def test_get_value(self):
        l = DeferredTuple(['one', Selector(0, None), 2])
        self.assertEqual(l.get_value({'objects': [1]}), ('one', 1, 2))
        self.assertEqual(l.get_value({'objects': ['one']}), ('one', 'one', 2))
