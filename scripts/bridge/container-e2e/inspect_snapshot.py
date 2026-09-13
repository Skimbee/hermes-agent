"""Runs only in trusted offline inspector after candidate container stops."""
import hashlib,json,os,stat,sys
payload=json.load(sys.stdin)
root=os.open('/snapshot/client',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
def parent(path):
    parts=path.split('/');assert parts and all(p not in ('','.','..') for p in parts)
    fd=os.dup(root)
    try:
        for p in parts[:-1]:
            new=os.open(p,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=new
        return fd,parts[-1]
    except:os.close(fd);raise

def read(path,limit=32*1024*1024):
    fd,name=parent(path)
    try:
        f=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd)
        try:
            st=os.fstat(f);assert stat.S_ISREG(st.st_mode) and st.st_size<=limit
            with os.fdopen(os.dup(f),'rb') as stream:return stream.read(limit+1),st.st_mode
        finally:os.close(f)
    finally:os.close(fd)
head=read('.git/HEAD',1024)[0].decode().strip()
if head.startswith('ref: '):
    ref=head[5:];assert ref.startswith('refs/heads/')
    head=read('.git/'+ref,1024)[0].decode().strip()
assert head==payload['candidate']
count=0
for entry in payload['manifest']:
    path=entry['path'];mode=entry['mode']
    if mode=='120000':
        fd,name=parent(path)
        try:data=os.readlink(name,dir_fd=fd).encode()
        finally:os.close(fd)
    else:
        assert mode in ('100644','100755')
        data,actual_mode=read(path)
        assert bool(actual_mode&0o111)==(mode=='100755'),path
        if entry.get('eol')=='crlf':
            normalized=data.replace(b'\r\n',b'\n')
            assert normalized.replace(b'\n',b'\r\n')==data, 'Noncanonical CRLF checkout: '+path
            data=normalized
    digest=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
    assert digest==entry['oid'],path
    count+=1
print(json.dumps({'post_head':head,'tracked_files_verified':count,'tracked_tree_matches':True,'candidate_stopped':True}))
