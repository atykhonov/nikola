# -*- coding: utf-8 -*-

# Copyright (c) 2012 Roberto Alsina y otros.

# Permission is hereby granted, free of charge, to any
# person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the
# Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the
# Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice
# shall be included in all copies or substantial portions of
# the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY
# KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
# WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
# PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS
# OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
# OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from __future__ import unicode_literals, print_function
import codecs
# import csv
import datetime
import os
import subprocess
import time

try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse  # NOQA

try:
    import feedparser
except ImportError:
    feedparser = None  # NOQA
from lxml import html
from mako.template import Template

from nikola.plugin_categories import Command
from nikola import utils

links = {}


class CommandImportFeed(Command):
    """Import a feed dump."""

    name = "import_feed"
    needs_config = False
    doc_usage = "[options] feed_file"
    doc_purpose = "Import a RSS/Atom dump."
    cmd_options = [
        {
            'name': 'output_folder',
            'long': 'output-folder',
            'short': 'o',
            'default': 'new_site',
            'help': 'Location to write imported content.'
        },
    ]

    def _execute(self, options, args):
        '''
            Import Atom/RSS feed
        '''

        # Parse the data
        if feedparser is None:
            print('To use the import_blogger command,'
                  ' you have to install the "feedparser" package.')
            return

        if not args:
            print(self.help())
            return

        options['filename'] = args[0]
        self.feed_export_file = options['filename']
        self.output_folder = options['output_folder']
        self.import_into_existing_site = False
        self.url_map = {}
        channel = self.get_channel_from_file(self.feed_export_file)
        self.context = self.populate_context(channel)
        conf_template = self.generate_base_site()
        self.context['REDIRECTIONS'] = self.configure_redirections(
            self.url_map)

        self.import_posts(channel)
        # self.write_urlmap_csv(
        #     os.path.join(self.output_folder, 'url_map.csv'), self.url_map)

        self.write_configuration(self.get_configuration_output_path(
        ), conf_template.render(**self.context))

    @classmethod
    def get_channel_from_file(cls, filename):
        if not os.path.isfile(filename):
            raise Exception("Missing file: %s" % filename)
        return feedparser.parse(filename)

    @staticmethod
    def populate_context(channel):
        context = {}
        context['DEFAULT_LANG'] = channel.feed.title_detail.language \
            if channel.feed.title_detail.language else 'en'
        context['BLOG_TITLE'] = channel.feed.title

        context['BLOG_DESCRIPTION'] = channel.feed.get('subtitle', '')
        context['SITE_URL'] = channel.feed.get('link', '').rstrip('/')
        context['BLOG_EMAIL'] = channel.feed.author_detail.get('email', '') if 'author_detail' in channel.feed else ''
        context['BLOG_AUTHOR'] = channel.feed.author_detail.get('name', '') if 'author_detail' in channel.feed else ''

        context['POST_PAGES'] = '''(
            ("posts/*.html", "posts", "post.tmpl", True),
            ("stories/*.html", "stories", "story.tmpl", False),
        )'''
        context['POST_COMPILERS'] = '''{
        "rest": ('.txt', '.rst'),
        "markdown": ('.md', '.mdown', '.markdown', '.wp'),
        "html": ('.html', '.htm')
        }
        '''

        return context

    @staticmethod
    def configure_redirections(url_map):
        redirections = []
        for k, v in url_map.items():
            # remove the initial "/" because src is a relative file path
            src = (urlparse(k).path + 'index.html')[1:]
            dst = (urlparse(v).path)
            if src == 'index.html':
                print("Can't do a redirect for: {0!r}".format(k))
            else:
                redirections.append((src, dst))

        return redirections

    def generate_base_site(self):
        if not os.path.exists(self.output_folder):
            subprocess.call(['nikola', 'init', self.output_folder])
        else:
            self.import_into_existing_site = True
            print('The folder {0} already exists - assuming that this is a '
                  'already existing nikola site.'.format(self.output_folder))

        conf_template = Template(filename=os.path.join(
            os.path.dirname(utils.__file__), 'conf.py.in'))

        return conf_template

    @staticmethod
    def write_configuration(filename, rendered_template):
        with codecs.open(filename, 'w+', 'utf8') as fd:
            fd.write(rendered_template)

    def get_configuration_output_path(self):
        if not self.import_into_existing_site:
            filename = 'conf.py'
        else:
            filename = 'conf.py.feed_import-{0}'.format(
                datetime.datetime.now().strftime('%Y%m%d_%H%M%s'))
        config_output_path = os.path.join(self.output_folder, filename)
        print('Configuration will be written to: ' + config_output_path)

        return config_output_path

    def import_posts(self, channel):
        for item in channel.entries:
            self.process_item(item)

    def process_item(self, item):
        self.import_item(item, 'posts')

    def import_item(self, item, out_folder=None):
        """Takes an item from the feed and creates a post file."""
        if out_folder is None:
            out_folder = 'posts'

        # link is something like http://foo.com/2012/09/01/hello-world/
        # So, take the path, utils.slugify it, and that's our slug
        link = item.link
        link_path = urlparse(link).path

        title = item.title

        # blogger supports empty titles, which Nikola doesn't
        if not title:
            print("Warning: Empty title in post with URL {0}. Using NO_TITLE "
                  "as placeholder, please fix.".format(link))
            title = "NO_TITLE"

        if link_path.lower().endswith('.html'):
            link_path = link_path[:-5]

        slug = utils.slugify(link_path)

        if not slug:  # should never happen
            print("Error converting post:", title)
            return

        description = ''
        post_date = datetime.datetime.fromtimestamp(time.mktime(
            item.published_parsed))

        for candidate in item.content:
            content = candidate.value
            break
                #  FIXME: handle attachments

        tags = []
        print(item.tags)
        for tag in item.tags:
            tags.append(tag.term)

        if item.get('app_draft'):
            tags.append('draft')
            is_draft = True
        else:
            is_draft = False

        self.url_map[link] = self.context['SITE_URL'] + '/' + \
            out_folder + '/' + slug + '.html'

        if is_draft and self.exclude_drafts:
            print('Draft "{0}" will not be imported.'.format(title))
        elif content.strip():
            # If no content is found, no files are written.
            content = self.transform_content(content)

            self.write_metadata(os.path.join(self.output_folder, out_folder,
                                             slug + '.meta'),
                                title, slug, post_date, description, tags)
            self.write_content(
                os.path.join(self.output_folder, out_folder, slug + '.html'),
                content)
        else:
            print('Not going to import "{0}" because it seems to contain'
                  ' no content.'.format(title))

    @classmethod
    def transform_content(cls, content):
        # No transformations yet
        return content

    @classmethod
    def write_content(cls, filename, content):
        doc = html.document_fromstring(content)
        doc.rewrite_links(replacer)

        with open(filename, "wb+") as fd:
            fd.write(html.tostring(doc, encoding='utf8'))

    @staticmethod
    def write_metadata(filename, title, slug, post_date, description, tags):
        with codecs.open(filename, "w+", "utf8") as fd:
            fd.write('\n'.join((title, slug, post_date.strftime('%Y/%M/%D %H:%m:%S'), ','.join(tags), '',
                                description)))


def replacer(dst):
    return links.get(dst, dst)