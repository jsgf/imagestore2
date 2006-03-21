# upload interface

# Uploading in three phases:
# - present form
#
# - show images found in the upload, with an option to set keywords,
# ownership. visibility, etc.  Images remain in a pending state until
# they're accepted into the main database.
#
# - once all that's OK, the images are put into the main database
#
# XXX how to represent?  separate flag?

import os, stat, sys
from traceback import extract_tb, format_list
from sets import Set
from zipfile import is_zipfile, ZipFile

from cStringIO import StringIO

from mx.DateTime import DateTime, gmt, gmtime

import quixote
from quixote.errors import AccessError, QueryError
from quixote.html import htmltext as H, TemplateIO
import quixote.http_response
import quixote.form as form2

from sqlobject.sqlbuilder import AND

import imagestore
import imagestore.db as db
import imagestore.insert as insert
import imagestore.search as search
import imagestore.image as image
import imagestore.calendarui as calendarui
import imagestore.pages as page

from form import userOptList, visibilityOptList, cameraOptList, splitKeywords

def is_zip_fp(fp):
    from zipfile import _EndRecData

    try:
        here = fp.tell()
        ret = _EndRecData(fp)
        fp.seek(here)
        return ret
    except IOError:
        pass
    return False

class UploadWorker:
    def __init__(self, files):
        self.files = files
        
class UploadUI:
    _q_exports = [ 'pending', 'commit' ]
    
    def __init__(self, collection):
        self.collection = collection

    def _q_access(self, request):
        user = request.session.getuser()
        perm = self.collection.dbobj.permissions(user)

        mayupload = (user and user.mayUpload) or (perm and perm.mayUpload)
        
        if not mayupload:
            raise AccessError, 'You may not upload images'

    def _q_index(self, request):
        return self.upload(request)

    def upload_form(self, request):
        user = request.session.getuser()
        
        form = form2.Form(action_url=request.get_path()+'#bottom',
                          name='picture-upload',
                          enctype='multipart/form-data')

        form.add(form2.StringWidget, name='keywords', title='Keywords',
                 hint='Default keywords for this upload')

        form.add(form2.SingleSelectWidget, name='camera', title='Camera',
                 hint='Camera used to take these pictures',
                 options=[ (-1, 'Guess', -1),
                           (-2, 'New Camera', -2) ] + cameraOptList())

        form.add(form2.SingleSelectWidget, name='visibility', title='Visibility',
                 options=['public', 'restricted', 'private'])

        form.add(form2.SingleSelectWidget, name='owner', title='Owner',
                 options = userOptList(), value=user.id)

        form.add(form2.HiddenWidget, name='numfiles', value=1)

        numfiles = int(form['numfiles'])

        form.add_submit('newfile', 'Add new file')
        form.add_reset('reset', 'Reset form values')
        
        display = not form.is_submitted()

        if form.get_submit() == 'newfile':
            numfiles += 1
            form.get_widget('numfiles').value = numfiles
            display = True
            
        for n in range(numfiles):
            name = 'file.%d' % n
            form.add(form2.FileWidget, name=name, title='File',
                     hint=(n == 0) and 'This may be multiple images, or an archive file' or None,
                     accept='image/*',
                     size=40)
            print 'form %s = %s' % (name, form[name])
            #form.get_widget(name).value = form[name]

        form.add_submit('upload', 'Upload file')

        return form

    def do_upload_zip(self, zipfp,
                      user, camera, keywords, visibility, upload):
        zip = ZipFile(zipfp, 'r')
        yield '<dl>\n'

        for f in zip.infolist():
            orig_name = f.filename
            mod_time = DateTime(*f.date_time)

            if orig_name[-1] == '/':
                continue

            for y in self.do_upload_file(StringIO(zip.read(orig_name)),
                                         orig_name, mod_time,
                                         user, camera, keywords, visibility, upload):
                yield y

        yield '</dl>\n'
        

    def do_upload_file(self, fp, base_file, date,
                       user, camera, keywords, visibility, upload):
        yield '<dt>Uploading <span class="filename">%s</span>&hellip;&nbsp;' % base_file
        
        if is_zip_fp(fp):
            yield '</dt>\n<dd>\n'
            for y in self.do_upload_zip(fp, user, camera, keywords, visibility, upload):
                yield y
            yield '</dd>\n'
        else:
            try:
                id = insert.import_image(datafp=fp,
                                         orig_filename=base_file,
                                         owner=user,
                                         photographer=user,
                                         public=visibility,
                                         collection=self.collection.dbobj,
                                         keywords=keywords,
                                         camera=camera,
                                         upload=upload,
                                         record_time=date)
                imageui = image.ImageUI(self.collection)
                r = H('OK, Picture #%s</dt><dd>%s</dd>\n') % \
                    (id, imageui.thumb_img(db.Picture.get(id), False))
            except insert.AlreadyPresentException, msg:
                r = H('</dt><dd>Already present (#%s)</dd>\n') % msg
            except insert.ImportException, msg:
                r = H('</dt><dd class="error">failed: %s</dd>\n') % msg
            except:
                (t,v,tb) = sys.exc_info()
                yield str(H('<pre>Unexpected error:\n%s %s:\n%s</pre>') % \
                          (t,v,''.join(format_list(extract_tb(tb)))))
                return
            yield str(r)

    def do_upload(self, request, files, user, camera, keywords, visibility, upload):
        r = page.pre(request, 'Uploading pictures', 'uploading', trail=False)
        r += H('<H1>Uploading pictures...</H1>\n')

        yield str(r)

        for (fp, base_filename) in files:
            for y in self.do_upload_file(fp, base_filename, None,
                                         user, camera, keywords, visibility, upload):
                yield y

        r = H('<p id="bottom"><a href="pending">Edit pending pictures</a>\n')
        r += H('<p><a href="%s">Upload more pictures</a>\n') % request.get_path()
        r += page.post()
        
        yield str(r)

    def upload(self, request):
        form = self.upload_form(request)
        
        if form.get_submit() != 'upload':
            r = TemplateIO(html=True)

            r += page.pre(request, 'Upload pictures', 'upload')
            r += page.menupane(request)
            r += form.render()

            #r += H(request.dump_html())
            
            r += page.post()

            return r.getvalue()
        else:
            user = request.session.getuser()
            start = calendarui.int_day.rounddown(gmt())
            end = calendarui.int_day.roundup(gmt())
            upload = db.Upload.select(AND(db.Upload.q.import_time >= start,
                                          db.Upload.q.import_time < end,
                                          db.Upload.q.userID == user.id,
                                          db.Upload.q.collectionID == self.collection.dbobj.id))

            assert upload.count() == 0 or upload.count() == 1, \
                   'Should be only one Upload per day per user'
            
            if upload.count() == 1:
                u = upload[0]
            else:
                u = db.Upload(user=user, collection=self.collection.dbobj)
            
            c = int(form['camera'])

            if c == -2:
                camera = None                    # new camera            
            elif c == -1:
                camera = None                    # guess
            else:
                camera = db.Camera.get(c)
                
            numfiles = int(form['numfiles'])

            keywords = form['keywords']
            if keywords is not None:
                keywords = splitKeywords(keywords)

            print 'self.collection.dbobj=%s' % self.collection.dbobj

            request.response.buffered=False
            upload = self.do_upload(request,
                                    [ (f.fp, f.base_filename)
                                      for f in [ form['file.%d' % n]
                                                 for n in range(numfiles) ]
                                      if f is not None],
                                    user, camera, keywords, form['visibility'], u)
            return quixote.http_response.Stream(upload)

    def pending(self, request):
        user = request.session.getuser()
        
        body = TemplateIO(html=True)

        results=[]

        for u in db.Upload.select(AND(db.Upload.q.collectionID == self.collection.dbobj.id,
                                      db.Upload.q.userID == user.id),
                                  orderBy=db.Upload.q.import_time):
            pics = u.pictures
            if not pics:
                continue

            pics.sort(lambda a,b: cmp(a.record_time, b.record_time))

            body += H('<div class="title-box upload">\n')
            body += H('<h2>Import into "%s" on %s</h2>\n') % (u.collection.name,
                                                           u.import_time.strftime('%Y-%m-%d')) # XXX

            for (d, pics) in search.group_by_time(pics, calendarui.int_day):
                body += H('<div id="%s" class="day">\n') % calendarui.int_day.num_fmt(d)
                body += H('<h3>%s</h3>\n') % calendarui.int_day.num_fmt(d)
                body += H('<div class="day-pics">\n')

                body += H('<form method="POST" action="commit">\n')

                kwset = [ k.word for k in search.commonKeywords(pics) ]
                kwset = ', '.join(list(kwset))
                
                body += H('<label>Default keywords: <input type="text" name="keywords" value="%s"></label>\n') % kwset
                body += H('<label>Visibility: <select name="visibility">\n')
                for v in ['unchanged', 'public', 'restricted', 'private']:
                    body += H('  <option value="%s">%s</option>\n') % (v, v.capitalize())
                body += H('</select></label>\n')
                
                for p in pics:
                    results.append(p)
                    body += H('<div style="float: left">\n')
                    body += image.ImageUI(self.collection).view_rotate_link(request, p, wantedit=True)
                    body += H('<br>\n')
                    body += H('<input title="Commit?" type="checkbox" name="pic" value="%d" checked>\n') % p.id
                    if p.keywords:
                        body += H('%s') % ', '.join([ k.word for k in p.keywords ])
                    
                    body += H('</div>\n')

                body += H('</div>\n')
                body += H('<br style="clear: both">')
                body += H('<input type="submit" name="defaults" value="Apply defaults">\n')
                body += H('<input type="submit" name="commit" value="Commit pictures to collection">\n')
                body += H('</form>\n')
                body += H('</div>\n')
            body += H('</div>\n')

        r = TemplateIO(html=True)

        request.session.set_query_results(results)

        r += page.pre(request, 'Pending uploaded images for "%s"' % self.collection.dbobj.name,
                      'pending', brieftitle='pending uploads')
        r += page.menupane(request)

        r += body.getvalue()

        r += page.post()

        return r.getvalue()
                    

    def have_pending(self, user):
        if not user:
            return False
        return db.Picture.select(AND(db.Picture.q.collectionID == self.collection.dbobj.id,
                                     db.Picture.q.uploadID == db.Upload.q.id,
                                     db.Picture.q.ownerID == user.id,
                                     db.Upload.q.userID == user.id)).count() != 0

    def path(self):
        return self.collection.path() + 'upload/'
    
    def pending_path(self):
        return self.path() + 'pending'

    def commit(self, request):
        user = request.session.getuser()

        print request.dump()

        if not request.form:
            raise QueryError, 'missing form'

        pics = request.form['pic']
        if not isinstance(pics, list):
            pics = [ pics ]

        if request.form.has_key('commit'):
            for p in pics:
                p = db.Picture.get(int(p))
                print 'p=%d p.upload=%s' % (p.id, p.upload)
                if p.upload is None:
                    continue

                if not user.mayAdmin and (not p.mayEdit(user) or p.upload.userID != user.id):
                    raise AccessError, "you can't commit this"
                p.upload = None

            if not self.have_pending(user):
                quixote.redirect(self.collection.path())

        elif request.form.has_key('defaults'):
            kw = splitKeywords(request.form['keywords'])
            vis = request.form['visibility']
            
            for p in pics:
                p = db.Picture.get(int(p))
                p.addKeywords(kw)
                if vis != 'unchanged':
                    p.visibility = vis
                
        quixote.redirect(self.pending_path())
        return ''
