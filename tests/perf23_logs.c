#include <assert.h>
#include <string.h>
#include <unistd.h>
#include "../src/runtime/pes13_perf23_logs.h"

static void check(const char *dir, int index, int expected)
{
    char path[1024];
    if(index) snprintf(path,sizeof(path),"%s/pes13-nx.previous-%d.log",dir,index);
    else snprintf(path,sizeof(path),"%s/pes13-nx.log",dir);
    FILE *f=fopen(path,"r"); assert(f); int value=0;
    assert(fscanf(f,"run %d",&value)==1 && value==expected); fclose(f);
}
int main(int argc,char **argv)
{
    assert(argc==2); int err; FILE *f;
    for(int i=1;i<=8;i++) {
        f=pes23_open_log(argv[1],&err); assert(f && !err);
        fprintf(f,"run %d\n",i); fclose(f);
        check(argv[1],0,i);
        for(int j=1;j<=4 && j<i;j++) check(argv[1],j,i-j);
    }
    /* Missing intermediate history must not prevent saving the latest run. */
    char path[1024]; snprintf(path,sizeof(path),"%s/pes13-nx.previous-2.log",argv[1]);
    assert(!remove(path));
    f=pes23_open_log(argv[1],&err); assert(f && !err); fputs("run 9\n",f); fclose(f);
    check(argv[1],1,8);
    /* A nonempty directory at a destination emulates a filesystem error;
     * the current run must survive, and subsequent logging appends. */
    snprintf(path,sizeof(path),"%s/pes13-nx.previous-3.log",argv[1]);
    f=fopen(path,"w"); assert(f); fputs("fixture\n",f); fclose(f);
    snprintf(path,sizeof(path),"%s/pes13-nx.previous-4.log",argv[1]);
    assert(!remove(path)); assert(!mkdir(path,0700));
    strncat(path,"/keep",sizeof(path)-strlen(path)-1); f=fopen(path,"w"); assert(f); fclose(f);
    f=pes23_open_log(argv[1],&err); assert(f && err); fputs("appended\n",f); fclose(f);
    check(argv[1],0,9);
    char huge[1100]; memset(huge,'x',sizeof(huge)-1); huge[sizeof(huge)-1]=0;
    assert(!pes23_open_log(huge,&err) && err==ENAMETOOLONG);
    puts("PERF23 log rotation 4 histories, gaps, fail-safe append, bounds PASS");
}
