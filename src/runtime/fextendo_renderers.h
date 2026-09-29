/* LGPL-2.1-or-later. Renderer files are installed before any guest DLL loads. */
#ifndef FEXTENDO_RENDERERS_H
#define FEXTENDO_RENDERERS_H
static const char *const fx_renderer_ids[2]={"dxvk-3.1.1","dxvk-2.7.1-async"};
static const char *const fx_renderer_names[2]={"DXVK 3.1.1","DXVK 2.7.1 async"};
static const char *const fx_renderer_targets[5]={
    "/drive_c/PES13/d3d9.dll","/drive_c/dxvk/d3d9.dll",
    "/drive_c/PES13/dxvk.conf","/launcher/presets/dxvk.conf","/launcher/renderer.txt"};
static int fx_renderer_selected(const char *root) {
    char p[768],b[2];snprintf(p,sizeof(p),"%s/launcher/renderer-choice.txt",root);
    return fx_read(p,b,2)==2&&b[0]=='1'&&b[1]=='\n';
}
static int fx_renderer_save(const char *root,int selected) {
    char p[768],b[2]={(char)('0'+selected),'\n'};
    if(selected<0||selected>1)return 0;
    snprintf(p,sizeof(p),"%s/launcher/renderer-choice.txt",root);
    return fx_write(p,b,2);
}
static int fx_renderer_recover(const char *root) {
    char journal[768],p[768],old[800],tmp[800];unsigned char mask;
    snprintf(journal,sizeof(journal),"%s/launcher/renderer.txn",root);
    if(access(journal,F_OK))return errno==ENOENT;
    if(fx_read(journal,&mask,1)!=1||(mask&~31))return 0;
    for(int i=0;i<5;i++){
        snprintf(p,sizeof(p),"%s%s",root,fx_renderer_targets[i]);
        snprintf(old,sizeof(old),"%s.fxr-old",p);snprintf(tmp,sizeof(tmp),"%s.fxr-new",p);
        if(!access(old,F_OK)){
            if(unlink(p)&&errno!=ENOENT)return 0;
            if(rename(old,p))return 0;
        }else if(!(mask&(1u<<i))&&unlink(p)&&errno!=ENOENT)return 0;
        else if((mask&(1u<<i))&&access(p,F_OK))return 0;
        unlink(tmp);
    }
    return !unlink(journal);
}
static int fx_files_equal(const char *a,const char *b) {
    unsigned char x[16384],y[16384];size_t nx,ny;int same=0;
    FILE *fa=fopen(a,"rb"),*fb=fopen(b,"rb");
    if(fa&&fb)do{
        nx=fread(x,1,sizeof(x),fa);ny=fread(y,1,sizeof(y),fb);
        if(nx!=ny||memcmp(x,y,nx)||ferror(fa)||ferror(fb))break;
        if(nx<sizeof(x)){same=1;break;}
    }while(1);
    if(fa)fclose(fa);if(fb)fclose(fb);return same;
}
static int fx_copy_file(const char *source,const char *target) {
    unsigned char buffer[16384];size_t n;int ok=0;
    FILE *in=fopen(source,"rb"),*out=NULL;if(!in)return 0;
    out=fopen(target,"wb");if(!out){fclose(in);return 0;}
    while((n=fread(buffer,1,sizeof(buffer),in)))if(fwrite(buffer,1,n,out)!=n)goto done;
    ok=!ferror(in)&&!fflush(out)&&!fsync(fileno(out));
done:
    fclose(in);if(fclose(out))ok=0;return ok;
}
static int fx_renderer_valid(const char *dll,const char *conf,int selected) {
    unsigned char head[64],pe[26];char config[4096];struct stat st;
    if(stat(dll,&st)||st.st_size<1024*1024||st.st_size>32*1024*1024)return 0;
    FILE *f=fopen(dll,"rb");if(!f)return 0;
    int ok=fread(head,1,64,f)==64&&head[0]=='M'&&head[1]=='Z';
    if(ok){uint32_t offset=fx_u32(head+60);
        ok=offset<=(uint64_t)st.st_size-26&&!fseek(f,(long)offset,SEEK_SET)&&
            fread(pe,1,26,f)==26&&!memcmp(pe,"PE\0\0\x4c\x01",6)&&pe[24]==0x0b&&pe[25]==1;}
    fclose(f);size_t n=fx_read(conf,config,sizeof(config)-1);config[n]=0;
    return ok&&n&&strstr(config,"d3d9.presentInterval = 1\n")&&
        (selected==0||strstr(config,"dxvk.enableAsync = True\n"));
}
static int fx_apply_renderer(const char *root,int selected) {
    char source[2][768],p[5][768],tmp[5][800],old[5][800],journal[768],journal_tmp[800];
    unsigned char mask=0;char choice[2]={(char)('0'+selected),'\n'};int same=1;
    if(selected<0||selected>1||!fx_renderer_recover(root)||!fx_recover(root))return 0;
    snprintf(source[0],sizeof(source[0]),"%s/launcher/renderers/%s/d3d9.dll",root,fx_renderer_ids[selected]);
    snprintf(source[1],sizeof(source[1]),"%s/launcher/renderers/%s/dxvk.conf",root,fx_renderer_ids[selected]);
    if(!fx_renderer_valid(source[0],source[1],selected))return 0;
    for(int i=0;i<5;i++){
        snprintf(p[i],sizeof(p[i]),"%s%s",root,fx_renderer_targets[i]);
        snprintf(tmp[i],sizeof(tmp[i]),"%.*s.fxr-new",767,p[i]);snprintf(old[i],sizeof(old[i]),"%.*s.fxr-old",767,p[i]);
        if(!fx_mkdir_parents(p[i]))return 0;
        if(!access(p[i],F_OK))mask|=1u<<i;
        if(i<4){if(!fx_files_equal(source[i/2],p[i]))same=0;}
        else {char b[2];if(fx_read(p[i],b,2)!=2||memcmp(b,choice,2))same=0;}
    }
    if(same)return 1; /* Read-only verification: do not rewrite multi-MB DLLs each launch. */
    for(int i=0;i<5;i++){
        if(i<4){if(!fx_copy_file(source[i/2],tmp[i])||!fx_files_equal(source[i/2],tmp[i]))goto failed;}
        else if(!fx_write(tmp[i],choice,2))goto failed;
    }
    for(int i=0;i<5;i++)if(unlink(old[i])&&errno!=ENOENT)goto failed;
    snprintf(journal,sizeof(journal),"%s/launcher/renderer.txn",root);
    snprintf(journal_tmp,sizeof(journal_tmp),"%s.tmp",journal);
    if(!fx_write(journal_tmp,&mask,1)||rename(journal_tmp,journal)){unlink(journal_tmp);goto failed;}
    for(int i=0;i<5;i++){
        if((mask&(1u<<i))&&rename(p[i],old[i]))goto rollback;
        if(rename(tmp[i],p[i]))goto rollback;
    }
    if(unlink(journal))goto rollback;
    for(int i=0;i<5;i++)unlink(old[i]);
    return 1;
rollback:
    fx_renderer_recover(root);return 0;
failed:
    for(int i=0;i<5;i++)unlink(tmp[i]);
    return 0;
}
#endif
