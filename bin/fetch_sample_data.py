# -*- coding: utf-8 -*-

# MIT/X11 License
#
# Copyright (c) 2019, Kungliga Tekniska högskolan
# (Royal Institute of Technology, Stockholm Sweden)
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import itertools
import sys

def fetch_data(datasource, registry, config):
    def eprint(*args, **kwargs):
        print(*args, file=sys.stderr, **kwargs)

    def split_list_string(s):
        for semi in s.split(";"):
            for comma in semi.split(","):
                yield comma

    # With input: [(key1, value_a), (key1, value_b), (key2, value_c), ...]
    # Output (as nested iterators): [(key1, [value_a, value_b]), (key2, [value_c])]
    def multivals_from_table(key_value_items):
        def keyfunc(item):
            return item[0]
        def valuefunc(item):
            return item[1]
        def filter_groups(key_and_key_values):
            (key, key_values) = key_and_key_values
            return (key, map(valuefunc, key_values))
        # we do not assume it is sorted by key
        l = list(key_value_items)
        l.sort(key=keyfunc)
        return map(filter_groups, itertools.groupby(l, key=keyfunc))

    for (userid,username) in datasource.fetch("SELECT uid,username FROM users ORDER BY uid,username;"):
        user = registry.all_users.get(userid, create=True)
        user.addresses.append(registry.all_emailaddresses.get(userid, create=True))
        user.username = username
        user.addresses.append(registry.all_emailaddresses.get(username, create=True))

    for (userid,aliases) in multivals_from_table(datasource.fetch("SELECT uid,alias FROM user_aliases ORDER BY uid;")):
        user = registry.all_users.get(userid)
        aliases = list(aliases) # from iterator
        for alias in aliases:
            if "@" in alias:
                registry.enabled_domains.add_from_email(alias)
        user.addresses += sorted([registry.all_emailaddresses.get(alias, create=True) for alias in aliases])

    for (userid,email_forward) in datasource.fetch("SELECT uid,email_forward FROM users;"):
        if email_forward is not None:
            user = registry.all_users.get(userid)
            for email_forward_sub in split_list_string(email_forward):
                email_forward_sub_clean = email_forward_sub.strip()
                try:
                    addr = registry.all_emailaddresses.get(email_forward_sub_clean, create=True)
                    user.add_email_forward(addr)
                except ValueError as e:
                    eprint("Warning: Excluding invalid email forward {} for {}".format(email_forward_sub_clean, user))

    for (groupid,aliases) in multivals_from_table(datasource.fetch("SELECT gid,email_alias FROM group_aliases;")):
        group = registry.all_groups.get(groupid, create=True)
        aliases = list(aliases) # from iterator
        for alias in aliases:
            if "@" in alias:
                registry.enabled_domains.add_from_email(alias)
        group.addresses += sorted([registry.all_emailaddresses.get(alias.strip(), create=True) for alias in aliases])

    for (groupid,email_recipients) in multivals_from_table(datasource.fetch("SELECT gid,email_recipient FROM group_email_recipients;")):
        group = registry.all_groups.get(groupid, create=True)
        for email_recipient in email_recipients:
            try:
                addr = registry.all_emailaddresses.get(email_recipient.strip(), create=True)
                group.add_email_recipient(addr)
            except ValueError as e:
                eprint("Warning: Excluding invalid email member {} for {}".format(email_recipient, group))

    cyclic_paths = []

    # Of all groups which have an associated email address,
    # gather recursive group_member contents.
    for (groupid,groupname,group_member_groupid,path,cycle) in datasource.fetch("""
WITH RECURSIVE search_email_groups(gid_of_group_with_email, gid_of_group_member, depth, path, cycle) AS (
        SELECT ga.gid, ga.gid::varchar(256), 1,
          ARRAY[ga.gid::varchar(256)]::varchar(256)[],
          false
        FROM group_aliases ga
      UNION ALL
        SELECT sg.gid_of_group_with_email, g.group_member::varchar(256), sg.depth + 1,
          (path || g.group_member::varchar(256))::varchar(256)[],
          g.group_member = ANY(path)
        FROM groups_in_groups g, search_email_groups sg
        WHERE g.gid = sg.gid_of_group_member AND NOT cycle
)
SELECT distinct grec.gid_of_group_with_email,gd.ug1name,grec.gid_of_group_member,grec.path,grec.cycle FROM search_email_groups AS grec, group_data AS gd WHERE grec.gid_of_group_with_email = gd.gid ORDER BY gd.ug1name;
"""):
        group = registry.all_groups.get(groupid, create=True)
        # FIXME only do once
        group.name = groupname
        group.add_member_group(registry.all_groups.get(group_member_groupid, create=True))
        if cycle:
            cyclic_paths.append([registry.all_groups.get(cycle_groupid, create=True) for cycle_groupid in path])

    # Most of these are not needed, but it's easier than complicating the recursive query.
    for (groupid,userid) in datasource.fetch("SELECT gid,uid FROM members_of_groups;"):
        group = registry.all_groups.get(groupid)
        if group is not None:
            group.add_member_user(registry.all_users.get(userid))

    cyclic_paths.sort()
    for path in cyclic_paths:
        if len(path) == 2 and path[0] == path[1]:
            eprint("Warning: Cyclic group memberships: {} is a direct member of itself".format(path[0]))
        else:
            eprint("Warning: Cyclic group memberships: {}".format(" has member ".join([str(group) for group in path])))

