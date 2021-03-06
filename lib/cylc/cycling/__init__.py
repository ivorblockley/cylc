#!/usr/bin/env python2

# THIS FILE IS PART OF THE CYLC SUITE ENGINE.
# Copyright (C) 2008-2018 NIWA
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""This module provides base classes for cycling data objects."""

from abc import ABCMeta, abstractmethod, abstractproperty


def parse_exclusion(expr):
    count = expr.count('!')
    if count == 0:
        return expr, None
    elif count > 1:
        raise Exception("'%s': only one set of exclusions per expression "
                        "permitted" % expr)
    else:
        remainder, exclusions = expr.split('!')
        if ',' in exclusions:
            if (not exclusions.strip().startswith('(') or not
                    exclusions.strip().endswith(')')):
                raise Exception("'%s': a list of exclusions must be "
                                "enclosed in parentheses." % exclusions)

        exclusions = exclusions.translate(None, ' ()')
        exclusions = exclusions.split(',')
        return remainder.strip(), exclusions


class CyclerTypeError(TypeError):

    """An error raised when incompatible cycling types are wrongly mixed."""

    ERROR_MESSAGE = "Incompatible cycling types: {0} ({1}), {2} ({3})"

    def __str__(self):
        return self.ERROR_MESSAGE.format(*self.args)


class PointParsingError(ValueError):

    """An error raised when a point has an incorrect value."""

    ERROR_MESSAGE = "Incompatible value for {0}: {1}: {2}"

    def __str__(self):
        return self.ERROR_MESSAGE.format(*self.args)


class IntervalParsingError(ValueError):

    """An error raised when an interval has an incorrect value."""

    ERROR_MESSAGE = "Incompatible value for {0}: {1}"

    def __str__(self):
        return self.ERROR_MESSAGE.format(*self.args)


class SequenceDegenerateError(Exception):

    """An error raised when adjacent points on a sequence are equal."""

    ERROR_MESSAGE = (
        "Sequence {0}, point format {1}: equal adjacent points: {2} => {3}.")

    def __str__(self):
        return self.ERROR_MESSAGE.format(*self.args)


class PointBase(object):

    """The abstract base class for single points in a cycler sequence.

    Points should be based around a string value.

    Subclasses should provide values for TYPE and TYPE_SORT_KEY.
    They should also provide self.cmp_, self.sub, self.add, and
    self.eq methods which should behave as __cmp__, __sub__,
    etc standard comparison methods. Note: "cmp_" not "cmp".

    Subclasses may also provide an overridden self.standardise
    method to reprocess their value into a standard form.

    """
    __metaclass__ = ABCMeta

    _TYPE = None
    _TYPE_SORT_KEY = None

    __slots__ = ('value')

    @abstractproperty
    def TYPE(self):
        return self._TYPE

    @abstractproperty
    def TYPE_SORT_KEY(self):
        return self._TYPE_SORT_KEY

    def __init__(self, value):
        if not isinstance(value, basestring):
            raise TypeError(type(value))
        self.value = value

    @abstractmethod
    def add(self, other):
        """Add other (interval) to self, returning a point."""
        pass

    def cmp_(self, other):
        """Compare self to other point, returning a 'cmp'-like result."""
        pass

    def standardise(self):
        """Format self.value into a standard representation and check it."""
        return self

    @abstractmethod
    def sub(self, other):
        """Subtract other (interval or point), returning a point or interval.

        If other is a Point, return an Interval.
        If other is an Interval, return a Point.

        ('Point' here is a PointBase-derived object, and 'Interval' an
         IntervalBase-derived object)

        """
        pass

    def __str__(self):
        # Stringify.
        return self.value

    __repr__ = __str__

    def __cmp__(self, other):
        # Compare to other point.
        if other is None:
            return -1
        if self.TYPE != other.TYPE:
            return cmp(self.TYPE_SORT_KEY, other.TYPE_SORT_KEY)
        if self.value == other.value:
            return 0
        return self.cmp_(other)

    def __sub__(self, other):
        # Subtract other (point or interval) from self.
        if self.TYPE != other.TYPE:
            raise CyclerTypeError(self.TYPE, self, other.TYPE, other)
        return self.sub(other)

    def __add__(self, other):
        # Add other (point or interval) from self.
        if self.TYPE != other.TYPE:
            raise CyclerTypeError(self.TYPE, self, other.TYPE, other)
        return self.add(other)


class IntervalBase(object):

    """An interval separating points in a cycler sequence.

    Intervals should be based around a string value.

    Subclasses should provide values for TYPE and TYPE_SORT_KEY.
    They should also provide self.cmp_, self.sub, self.add,
    self.__mul__, self.__abs__, self.__nonzero__ methods which should
    behave as __cmp__, __sub__, etc standard comparison methods.

    They can also just override the provided comparison methods (such
    as __cmp__) instead.

    Note: "cmp_" not "cmp", etc. They should also provide:
     * self.get_null, which is a method to extract the null interval of
    this type.
     * self.get_null_offset, which is a method to extract a null offset
    relative to a PointBase object.
     * self.get_inferred_child to generate an offset from an input
    without units using the current units of the instance (if any).

    Subclasses may also provide an overridden self.standardise
    method to reprocess their value into a standard form.

    """
    __metaclass__ = ABCMeta

    _TYPE = None
    _TYPE_SORT_KEY = None

    __slots__ = ('value')

    @abstractproperty
    def TYPE(self):
        return self._TYPE

    @abstractproperty
    def TYPE_SORT_KEY(self):
        return self._TYPE_SORT_KEY

    @classmethod
    @abstractmethod
    def get_null(cls):
        """Return a null interval."""
        pass

    @abstractmethod
    def get_inferred_child(self, string):
        """For a given string, infer the offset given my instance units."""
        pass

    @abstractmethod
    def __abs__(self):
        # Return an interval with absolute values for all properties.
        pass

    @abstractmethod
    def __mul__(self, factor):
        # Return an interval with all properties multiplied by factor.
        pass

    @abstractmethod
    def __nonzero__(self):
        # Return True if the interval has any non-zero properties.
        pass

    def __init__(self, value):
        if not isinstance(value, basestring):
            raise TypeError(type(value))
        self.value = value

    @abstractmethod
    def add(self, other):
        """Add other to self, returning a Point or Interval.

        If other is a Point, return a Point.
        If other is an Interval, return an Interval..

        ('Point' here is a PointBase-derived object, and 'Interval' an
         IntervalBase-derived object)

        """
        pass

    @abstractmethod
    def cmp_(self, other):
        """Compare self to other (interval), returning a 'cmp'-like result."""
        pass

    def standardise(self):
        """Format self.value into a standard representation."""
        return self

    @abstractmethod
    def sub(self, other):
        """Subtract other (interval) from self; return an interval."""
        pass

    def is_null(self):
        return (self == self.get_null())

    def __str__(self):
        # Stringify.
        return self.value

    def __add__(self, other):
        # Add other (point or interval) to self.
        if self.TYPE != other.TYPE:
            raise CyclerTypeError(self.TYPE, self, other.TYPE, other)
        return self.add(other)

    def __cmp__(self, other):
        # Compare self to other (interval).
        if self.TYPE != other.TYPE:
            return cmp(self.TYPE_SORT_KEY, other.TYPE_SORT_KEY)
        if self.value == other.value:
            return 0
        return self.cmp_(other)

    def __sub__(self, other):
        # Subtract other (interval or point) from self.
        if self.TYPE != other.TYPE:
            raise CyclerTypeError(self.TYPE, self, other.TYPE, other)
        return self.sub(other)

    def __neg__(self):
        # Return an interval with all properties multiplied by -1.
        return self * -1


class SequenceBase(object):

    """The abstract base class for cycler sequences.

    Subclasses should accept a sequence-specific string, a
    start context string, and a stop context string as
    constructor arguments.

    Subclasses should provide values for TYPE and TYPE_SORT_KEY.
    They should also provide get_async_expr, get_interval,
    get_offset & set_offset (deprecated), is_on_sequence,
    get_nearest_prev_point, get_next_point,
    get_next_point_on_sequence, get_first_point, and
    get_stop_point.

    They should also provide a self.__eq__ implementation
    which should return whether a SequenceBase-derived object
    is equal to another (represents the same set of points).

    """
    __metaclass__ = ABCMeta

    _TYPE = None
    _TYPE_SORT_KEY = None

    __slots__ = ()

    @abstractproperty
    def TYPE(self):
        return self._TYPE

    @abstractproperty
    def TYPE_SORT_KEY(self):
        return self._TYPE_SORT_KEY

    @classmethod
    @abstractmethod  # Note: stacked decorator not strictly enforced in Py2.x
    def get_async_expr(cls, start_point=0):
        """Express a one-off sequence at the initial cycle point."""
        pass

    @abstractmethod
    def __init__(self, sequence_string, context_start, context_stop=None):
        """Parse sequence string according to context point strings."""
        pass

    @abstractmethod
    def get_interval(self):
        """Return the cycling interval of this sequence."""
        pass

    @abstractmethod
    def get_offset(self):
        """Deprecated: return the offset used for this sequence."""
        pass

    @abstractmethod
    def set_offset(self, i_offset):
        """Deprecated: alter state to offset the entire sequence."""
        pass

    @abstractmethod
    def is_on_sequence(self, point):
        """Is point on-sequence, disregarding bounds?"""
        pass

    @abstractmethod
    def is_valid(self, point):
        """Is point on-sequence and in-bounds?"""
        pass

    @abstractmethod
    def get_prev_point(self, point):
        """Return the previous point < point, or None if out of bounds."""
        pass

    @abstractmethod
    def get_nearest_prev_point(self, point):
        """Return the largest point < some arbitrary point."""
        pass

    @abstractmethod
    def get_next_point(self, point):
        """Return the next point > point, or None if out of bounds."""
        pass

    @abstractmethod
    def get_next_point_on_sequence(self, point):
        """Return the next point > point assuming that point is on-sequence,
        or None if out of bounds."""
        pass

    @abstractmethod
    def get_first_point(self, point):
        """Return the first point >= to point, or None if out of bounds."""
        pass

    @abstractmethod
    def get_stop_point(self):
        """Return the last point in this sequence, or None if unbounded."""
        pass

    @abstractmethod
    def __eq__(self, other):
        # Return True if other (sequence) is equal to self.
        pass


class ExclusionBase(object):
    """A collection of points or sequences that are treated in an
    exclusionary manner"""

    __metaclass__ = ABCMeta
    __slots__ = ('exclusion_sequences', 'exclusion_points',
                 'exclusion_start_point', 'exclusion_end_point')

    def __init__(self, start_point, end_point=None):
        """creates an exclusions object that can contain integer points
        or integer sequences to be used as excluded points."""
        self.exclusion_sequences = []
        self.exclusion_points = []
        self.exclusion_start_point = start_point
        self.exclusion_end_point = end_point

    @abstractmethod
    def build_exclusions(self, excl_points):
        """Constructs the set of exclusion sequences or points"""
        pass

    def __contains__(self, point):
        """Checks to see if the Exclusions object contains a point
        in any of the exclusion sequences.

        Args:
            point (str): The time point to check lies in the
                ISO8601Sequence object.
        """
        if point in self.exclusion_points:
            return True
        if any(seq.is_valid(point) for seq in self.exclusion_sequences):
            return True
        return False

    def __getitem__(self, key):
        """Allows indexing of the exclusion object"""
        return self.exclusion_sequences[key]

    def __str__(self):
        returns = []
        for point in sorted(self.exclusion_points):
            returns.append(str(point))
        for sequence in self.exclusion_sequences:
            returns.append(str(sequence))
        ret = ','.join(returns)
        if ',' in ret:
            ret = '(' + ret + ')'
        return ret


if __name__ == "__main__":
    import unittest

    class TestBaseClasses(unittest.TestCase):
        """Test the abstract base classes cannot be instantiated on their own
        """
        def test_simple_abstract_class_test(self):
            """Cannot instantiate abstract classes, they must be defined in
            the subclasses"""
            self.assertRaises(TypeError, SequenceBase, "sequence-string",
                              "context_string")
            self.assertRaises(TypeError, IntervalBase, "value")
            self.assertRaises(TypeError, PointBase, "value")

    class TestParseExclusion(unittest.TestCase):
        """Test cases for the parser function"""
        def test_parse_exclusion_simple(self):
            """Tests the simple case of exclusion parsing"""
            expression = "PT1H!20000101T02Z"
            sequence, exclusion = parse_exclusion(expression)

            self.assertEqual(sequence, "PT1H")
            self.assertEqual(exclusion, ['20000101T02Z'])

        def test_parse_exclusions_list(self):
            """Tests the simple case of exclusion parsing"""
            expression = "PT1H!(T03, T06, T09)"
            sequence, exclusion = parse_exclusion(expression)

            self.assertEqual(sequence, "PT1H")
            self.assertEqual(exclusion, ['T03', 'T06', 'T09'])

        def test_parse_exclusions_list_spaces(self):
            """Tests the simple case of exclusion parsing"""
            expression = "PT1H!    (T03, T06,   T09)   "
            sequence, exclusion = parse_exclusion(expression)

            self.assertEqual(sequence, "PT1H")
            self.assertEqual(exclusion, ['T03', 'T06', 'T09'])

        def test_parse_bad_exclusion(self):
            """Tests incorrectly formatted exclusions"""
            expression1 = "T01/PT1H!(T06, T09), PT5M"
            expression2 = "T01/PT1H!T03, PT17H, (T06, T09), PT5M"
            expression3 = "T01/PT1H! PT8H, (T06, T09)"
            expression4 = "T01/PT1H! T03, T06, T09"

            self.assertRaises(Exception, parse_exclusion, expression1)
            self.assertRaises(Exception, parse_exclusion, expression2)
            self.assertRaises(Exception, parse_exclusion, expression3)
            self.assertRaises(Exception, parse_exclusion, expression4)

    unittest.main()
