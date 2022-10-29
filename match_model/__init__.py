# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which can be found at http://www.apache.org/licenses/LICENSE-2.0.

# Modifications copyright (c) 2022 The MATCH Authors. All rights reserved.
# Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE Version 3 (or later), which is in the LICENSE file.

"""
This package defines the MATCH model for Pyomo.

core_modules is a list of required modules which may be used in the future
for error checking.

An additional module is required to describe fuel costs - either
fuel_cost which specifies a simple flat fuel cost that can vary by load
zone and period, or fuel_markets which specifies a tiered supply curve.


Most applications of MATCH will also benefit from optional modules such as
transmission, local_td, reserves, etc.
"""
from .version import __version__

core_modules = [
    "match_model.timescales",
    "match_model.financials",
    "match_model.balancing.load_zones",
    "match_model.generators",
    "match_model.reporting",
]
