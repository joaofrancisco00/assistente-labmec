# Compila as soluções de referência contra o NeoPZ real instalado.
#
# Este é o teste de verdade das receitas: se algo aqui parar de compilar,
# a receita correspondente (e a página da wiki gerada a partir dela) está
# ensinando código quebrado ao assistente — corrigir antes de reindexar.
#
# Uso:
#   cmake -S reference_solutions -B reference_solutions/build \
#         -DNeoPZ_DIR=/opt/neopz/lib/cmake/neopz
#   cmake --build reference_solutions/build -j4

cmake_minimum_required(VERSION 3.14)
project(ReceitasLabMeC CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(NeoPZ REQUIRED)

add_executable(poisson2d      task_03_poisson2d/poisson.cpp)
add_executable(elasticidade2d task_04_elasticidade2d/elasticidade.cpp)
add_executable(darcy_misto2d  task_05_darcy_misto/darcy_misto.cpp)

foreach(alvo poisson2d elasticidade2d darcy_misto2d)
    target_link_libraries(${alvo} PRIVATE NeoPZ::pz)
    target_include_directories(${alvo} PRIVATE ${PZ_INCLUDE_DIRS})
endforeach()
