#include <stdlib.h>
#include <stdio.h>
#include <stdint.h>
#include <math.h>

int main(int argc, char* argv[]){
    long num;
    char* endptr;
    for (int i = 1; i < argc; i++){
        num = atol(argv[i]);
        if (num % 2 == 0 || num % 3 == 0 || num % 5 == 0){
            continue;
        }
        //1,7,11,13,17,19,23,29
        int increments[8] = {6, 4, 2, 4, 2, 4, 6, 2};
        long n = 7;
        int index = 1;
        long sq = (long)sqrt((double)num) + 1;
        while (n <= sq){
            if (num % n == 0){
                break;
            }
            n += increments[index];
            index = (index + 1) % 8;
        }
        if (n > sq){
            printf("%ld\n", num);
        }
    }
}
