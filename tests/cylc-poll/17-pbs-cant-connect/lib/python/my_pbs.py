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

import os


from cylc.batch_sys_handlers.pbs import PBSHandler


class MyPBSHandler(PBSHandler):
    """For testing poll command connection refused."""
    @staticmethod
    def get_poll_many_cmd(_):
        """Always print PBSHandler.POLL_CANT_CONNECT_ERR to STDERR."""
        return os.path.join(os.path.dirname(__file__), 'badqstat')


BATCH_SYS_HANDLER = MyPBSHandler()
